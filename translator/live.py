"""Live skill: a 25 Hz loop driven by the card, instead of a plan made once and replayed.

Every tick: look (the robot's own cameras), ask which card step is true now, command one IK step. Move the object and
the hand re-aims; knock it out of the gripper and the robot goes back and picks it up; take it out of the container
and it starts again. No training and no robot-specific code: the card says what the steps are and what "done" means.

Measured, not assumed: where the object and container are (cameras), holding (contact between fingers and object, a
stand-in for a gripper force sensor, plus the cameras when they see it). Simulator truth is used for one thing only:
scoring a trial, the same test as everywhere else (`Scene.cube_in_bowl`). `eyes=False` reads true poses instead of
the cameras and is marked as such in every result.

  lv = Live("ur5e", card, seed=0, stick=True)   # or Live(scene, card) for a scene that is already reset
  lv.step()                         # one 25 Hz tick: look, decide, one IK step, physics
  lv.move_object(xy)                # puts the object at xy (a teleport: say "moved", not "pushed")
  lv.knock()                        # with stick=True a real hit with contact forces, else a teleport
  lv.state()                        # {"step", "held", "tries", "recoveries", "success", ...}
No viewer, rendering or recording in here: drive it with step() and read `scene.data`.
"""
import math
import time
from collections import deque

import mujoco
import numpy as np

from .execute import FPS, GRIP_TIME, _rot_angle, _slerp
from .ik import IK
from .perceive import LOOK_CAMERAS, ROLE_MASKS, TOP_FACE, Eyes, _box_yaw, _circle_centre, _world_points
from .scene import _MOVABLE, TABLE_TOP, Scene, build, sample_layout
from .translate import SETTLE, _waypoints, grip_options, translate

ACCEL = 4.0  # m/s^2, the commanded hand's limit: a held object must not be shaken loose
STIFF = 6.0  # 1/s, how fast the commanded hand closes on its target
NEAR = 0.003  # m, arrived at a target
STILL = 0.004  # m, the object moved less than this over STILL_S counts as lying still
STILL_S = 0.3
MOVED = 0.015  # m, the object left the spot the hand is going down to
LOST_S = 0.12  # s without a hold before it counts as dropped
SEEN_HIGH = 0.35  # m above the table the cameras keep looking for the object
TRIM = 0.1  # per tick, how fast the hand's measured position (joint encoders) corrects the servos' steady error
TRIM_MAX = 0.025  # m


def free_spot(scene: Scene, rng, away_from, lo, hi):
    """A free spot on the table lo..hi m from `away_from`, where layouts come from, clear of the container."""
    clearance = scene.held_xy + 0.02
    near, far = max(0.35 * scene.reach, scene.footprint + clearance), 0.75 * scene.reach
    bowl = scene.bowl_pos()[:2]
    for _ in range(5000):
        r, a = rng.uniform(near, far), rng.uniform(-math.pi / 4, math.pi / 4)
        xy = scene.origin[:2] + r * np.array([math.cos(a), math.sin(a)])
        if (lo <= np.linalg.norm(xy - away_from) <= hi and scene.on_table(xy, clearance) and scene.clear_of_robot(xy, clearance)
                and np.linalg.norm(xy - bowl) >= scene.container_xy + scene.held_xy + 0.025):
            return xy
    return None


def put(scene: Scene, xy, drop=0.0):
    """Move the object to `xy`, `drop` m above the table: the scripted hand of a person."""
    m, d = scene.model, scene.data
    a = scene.cube_qadr
    d.qpos[a:a + 3] = [xy[0], xy[1], TABLE_TOP + scene.held_half + 0.001 + drop]
    v = m.jnt_dofadr[m.joint("cube").id]
    d.qvel[v:v + 6] = 0
    mujoco.mj_forward(m, d)


class Stick:
    """A person's stick: a kinematic capsule that really touches things (build(..., stick=True)), so a shove is
    ordinary contact physics, not a moved object. Moved every physics step through MuJoCo's control callback."""

    def __init__(self, scene: Scene):
        self.scene = scene
        m = scene.model
        self.mocap = int(m.body_mocapid[m.body("stick").id])
        self.a, self.b, self.t, self.T = None, None, 0.0, 0.0
        mujoco.set_mjcb_control(self)

    def __call__(self, m, d):
        if self.a is None:
            return
        self.t += m.opt.timestep
        s = self.t / self.T
        if s >= 1.2:
            d.mocap_pos[self.mocap] = [0, 0, -1]
            self.a = None
            return
        d.mocap_pos[self.mocap] = self.a + min(s, 1.0) * (self.b - self.a)

    def shove(self, start_xy, end_xy, z, speed):
        """Sweep from `start_xy` to `end_xy` with the stick's centre at height `z`."""
        self.a = np.array([start_xy[0], start_xy[1], z])
        self.b = np.array([end_xy[0], end_xy[1], z])
        self.t, self.T = 0.0, float(np.linalg.norm(self.b - self.a)) / speed

    def on_table(self, rng, lo=0.05, hi=0.12):
        """Push the object along the table to a free spot lo..hi m away; the path stays clear of the container."""
        s = self.scene
        c, bowl = s.cube_pos()[:2], s.bowl_pos()[:2]
        for _ in range(50):
            xy = free_spot(s, rng, c, lo, hi)
            if xy is None:
                return False
            d = (xy - c) / np.linalg.norm(xy - c)
            t = np.clip(np.dot(bowl - c, d), 0.0, np.linalg.norm(xy - c))
            if np.linalg.norm(c + t * d - bowl) > s.container_xy + s.held_xy + 0.01:
                self.shove(c - d * (s.held_xy + 0.06), xy - d * (s.held_xy + 0.013), TABLE_TOP + 0.003 + 0.162, 0.5)
                return True
        return False

    def out_of_hand(self, rng):
        """Hit the held object sideways: across the hand's third axis, out between the fingers."""
        s = self.scene
        r = s.robot
        third = 3 - "xyz".index(r.approach_axis[1]) - "xyz".index(r.closing_axis[1])
        d = s.ee_rot()[:, third][:2]
        d = d / max(np.linalg.norm(d), 1e-6) * rng.choice([-1.0, 1.0])
        c = s.cube_pos()
        self.shove(c[:2] - d * (s.held_xy + 0.05), c[:2] + d * 0.12, c[2] + 0.05, 1.2)
        return True


class Tracker(Eyes):
    """One front + top render per look, both objects from the same images, at any height (`Eyes.find` renders per
    object and only looks near the table). Same masks, same depth geometry."""

    def __init__(self, scene: Scene, card):
        super().__init__(scene)
        self.card = card
        self.held = card["grip"]["object"]
        self.cont = card["success"]["container"]

    def look(self, want_bowl=True, want_yaw=True):
        s = self.scene
        m, d = s.model, s.data
        spec, box = self.card["objects"][self.held], self.card["objects"][self.cont]
        high = TABLE_TOP + SEEN_HIGH
        held, bowl = [], []
        for camera in LOOK_CAMERAS:
            self.rgb.update_scene(d, camera=camera)
            self.depth.update_scene(d, camera=camera)
            rgb, depth = self.rgb.render(), self.depth.render()
            p = _world_points(m, d, camera, depth, ROLE_MASKS["held"](rgb))
            held.append(p[(p[:, 2] > TABLE_TOP - 0.01) & (p[:, 2] < high)])
            if want_bowl:
                p = _world_points(m, d, camera, depth, ROLE_MASKS["container"](rgb))
                bowl.append(p[(p[:, 2] > TABLE_TOP - 0.01) & (p[:, 2] < TABLE_TOP + box["wall_height"] + 0.02)])
        held = np.concatenate(held)
        found = {"held": None, "yaw": None, "pixels": len(held), "bowl": None}
        if len(held) >= 20:
            h = spec["size"][2]
            top = np.percentile(held[:, 2], 97)
            on_table = top < TABLE_TOP + 1.3 * h
            face = held[held[:, 2] > (TABLE_TOP + TOP_FACE * h if on_table else top - max(0.1 * h, 0.004))]
            face = face if len(face) >= 20 else held
            xy = face[:, :2].mean(axis=0)
            found["held"] = np.array([xy[0], xy[1], TABLE_TOP + h / 2 if on_table else top - h / 2])
            found["pixels"] = len(face)
            if want_yaw and spec["shape"] == "box":
                found["yaw"] = _box_yaw(face[:, :2], spec["size"])
        if want_bowl:
            bowl = np.concatenate(bowl)
            if len(bowl) >= 20:
                rim = bowl[bowl[:, 2] > TABLE_TOP + 0.75 * box["wall_height"]]
                if len(rim) < 20:
                    xy = bowl[:, :2].mean(axis=0)
                elif box["shape"] == "box":
                    xy = (rim[:, :2].min(axis=0) + rim[:, :2].max(axis=0)) / 2
                else:
                    xy = _circle_centre(rim[::3, :2])
                found["bowl"] = np.array([xy[0], xy[1], TABLE_TOP])
        return found


class Live:
    def __init__(self, robot, card, seed=0, look_every=2, eyes=True, bowl_every=25, stick=False):
        """`robot`: a library name (builds the scene, layout from `seed`) or a Scene that is already reset."""
        if not isinstance(robot, Scene):
            scene = build(robot, card, stick=stick)
            if scene.refusal:
                raise ValueError(f"{scene.refusal[0]}: {scene.refusal[1]}")
            scene.reset(*sample_layout(scene, np.random.default_rng(seed)))
            robot = scene
        scene = robot
        self.scene, self.card = scene, card
        self.rng = np.random.default_rng(seed + 1)
        self.stick = Stick(scene) if stick else None
        self.eyes = Tracker(scene, card) if eyes else None
        self.look_every, self.bowl_every = look_every, bowl_every
        self.held, self.cont = card["grip"]["object"], card["success"]["container"]
        self.order = [s["do"] for s in card["steps"]]
        m = scene.model
        self.acts = [a for a in scene.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
        self.physics = round(1 / FPS / m.opt.timestep)
        self.hand_geoms = set(scene._hand_geoms())
        self.object_body = m.body("cube").id
        self.ik = IK(scene)
        self.check_ik = IK(scene)
        self.limited = [(int(m.jnt_qposadr[j]), *m.jnt_range[j]) for j in range(m.njnt)
                        if m.jnt_limited[j] and m.jnt_type[j] in _MOVABLE]
        self.x, self.v, self.R = scene.ee_pos(), np.zeros(3), scene.ee_rot()
        self.trim = np.zeros(3)
        self.q, self.quiet = None, 0
        self.can_trim = len(scene.arm_joints) >= 6  # with 5 joints a position fix would tilt the hand instead
        self.home = (self.x.copy(), self.R.copy())
        self.grip, self.closed = 0.0, False
        self.n, self.since, self.settled, self.lost_ticks = 0, 0, 0, 0
        self.obj, self.yaw, self.bowl = None, 0.0, None
        self.best, self.best_pixels = None, 0
        self.track = deque(maxlen=max(2, round(STILL_S * FPS / look_every)))
        self.doing, self.rot, self.target, self.locked = None, self.R, self.x.copy(), None
        self.fresh_grip = True
        self.tries, self.recoveries = 1, 0
        self.d0, self.dist = 0.0, 0.0
        self.events = []
        self.ms = {"look": [], "ik": [], "physics": [], "tick": []}
        self.seen_err = []
        self.look(force=True)
        self.goto("reach")

    def say(self, text):
        self.events.append((self.n, text))

    def goto(self, step):
        self.doing, self.since, self.settled = step, 0, 0
        self.d0 = float(np.linalg.norm(self.x - self.target))

    def next_step(self, after=None):
        i = self.order.index(after or self.doing) + 1
        self.goto(self.order[i] if i < len(self.order) else "done")

    def look(self, force=False):
        s = self.scene
        if not self.eyes:  # simulator truth, only with eyes=False
            t = s.true_objects()
            self.obj, self.yaw, self.bowl = t[self.held]["pos"], t[self.held]["yaw"], t[self.cont]["pos"]
            self.best = self.obj.copy()
            self.track.append(self.obj.copy())
            return
        want_bowl = force or self.bowl is None or self.n % self.bowl_every == 0
        got = self.eyes.look(want_bowl, self.doing in (None, "reach"))
        if got["bowl"] is not None:
            self.bowl = got["bowl"]
        if got["held"] is not None:
            self.obj = got["held"]
            self.track.append(self.obj.copy())
            moved = self.best is None or np.linalg.norm(self.obj[:2] - self.best[:2]) > 0.01
            clear = np.linalg.norm(self.obj[:2] - s.ee_pos()[:2]) > 0.10
            if moved or (clear and got["pixels"] >= self.best_pixels):  # the arm hides part of it: only views from when the hand was away
                self.best, self.best_pixels = self.obj.copy(), got["pixels"]
                self.yaw = got["yaw"] if got["yaw"] is not None else self.yaw
            self.seen_err.append(float(np.linalg.norm(self.obj[:2] - s.cube_pos()[:2])))

    def still(self):
        if len(self.track) < self.track.maxlen:
            return False
        pts = np.array(self.track)
        return float(np.ptp(pts, axis=0).max()) < STILL

    def in_container(self):
        """The card's success test on what the cameras see."""
        s = self.scene
        if self.obj is None or self.bowl is None:
            return False
        inner = s.bowl_radius - float(s.objs["held_size"][0]) / 2
        d = self.obj[:2] - self.bowl[:2]
        off = np.abs(d).max() if s.square_bin else np.linalg.norm(d)
        return bool(off < inner + 0.005 and self.obj[2] < TABLE_TOP + max(s.bowl_wall, 0.021 + s.held_half))

    def can_reach(self):
        r = float(np.linalg.norm(self.obj[:2] - self.scene.origin[:2]))
        return r < 0.95 * self.scene.reach and self.scene.on_table(self.obj[:2], 0.0)

    def touching(self):
        m, d = self.scene.model, self.scene.data
        for c in d.contact[:d.ncon]:
            a, b = int(c.geom1), int(c.geom2)
            if (m.geom_bodyid[a] == self.object_body and b in self.hand_geoms) or \
                    (m.geom_bodyid[b] == self.object_body and a in self.hand_geoms):
                return True
        return False

    def holding(self):
        """Fingers on the object now; when the cameras see it, it must also be at the hand."""
        if not self.touching():
            return False
        return self.obj is None or float(np.linalg.norm(self.obj - self.scene.ee_pos())) < 0.12

    def seen(self):
        pos = self.locked if self.locked is not None and self.doing != "reach" else self.best
        return {self.held: {"pos": pos, "yaw": self.yaw}, self.cont: {"pos": self.bowl}}

    def waypoints(self):
        return {w.label: w for w in _waypoints(self.card, self.scene, self.seen(), self.rot)}

    def miss(self, waypoints):
        """Like execute.reach_miss, from the live state: physics leaves joints a hair outside their limits (Robotiq
        fingers), which the IK's QP cannot start from, so the pose is clipped first."""
        q = self.scene.data.qpos.copy()
        for a, lo, hi in self.limited:
            q[a] = np.clip(q[a], lo + 1e-6, hi - 1e-6)
        ik = self.check_ik
        ik.cfg.update(q)
        worst = 0.0
        for wp in waypoints:
            if wp.pos is None:
                continue
            for _ in range(4):
                _, pe, _ = ik.solve(wp.pos, wp.rot, 0.25)
            if wp.label in ("descend", "lift", "carry", "lower"):
                worst = max(worst, pe)
        return worst

    def choose_grip(self):
        """A new attempt: the reachable grip with the least wrist turn, like the plan-once path."""
        wps = translate(self.card, self.scene, {self.held: {"pos": self.best, "yaw": self.yaw}, self.cont: {"pos": self.bowl}},
                        check=self.miss)
        self.rot = wps[0].rot
        self.fresh_grip = False

    def turn_with_object(self):
        spec = self.card["objects"][self.held]
        if spec["shape"] != "box":
            return
        size, width = spec["size"], self.card["grip"].get("width")
        self.rot = grip_options(self.scene.robot, self.yaw, self.rot, size, width)[0]

    def over_container(self, hand, target):
        """The straight way from the hand to the target passes over the container."""
        a, b, c = hand[:2], target[:2], self.bowl[:2]
        ab = b - a
        t = np.clip(np.dot(c - a, ab) / max(np.dot(ab, ab), 1e-9), 0.0, 1.0)
        return float(np.linalg.norm(a + t * ab - c)) < self.scene.container_xy + 0.08

    def decide(self):
        step = self.doing
        if step in ("lift", "carry", "lower") and self.since / FPS > 0.1:
            self.lost_ticks = 0 if self.holding() else self.lost_ticks + 1
            if self.lost_ticks >= round(LOST_S * FPS):
                self.say("lost it: going back")
                self.recoveries += 1
                self.tries += 1
                self.closed, self.fresh_grip, self.locked, self.lost_ticks = False, True, None, 0
                self.goto("reach")
                step = "reach"
        target, rot, speed = self.x.copy(), self.R, 1.0
        if step == "reach":
            self.closed, self.locked = False, None
            if self.obj is None:
                self.target = target
                return target, rot, speed
            if self.still() and self.in_container():
                self.say("it is in the container")
                self.goto("done")
                return self.home[0], self.home[1], 1.0
            if not self.can_reach():
                self.target = target
                return target, rot, speed
            if self.fresh_grip and self.still():
                self.choose_grip()
            elif not self.fresh_grip:
                self.turn_with_object()
            wps = self.waypoints()
            target, rot = wps["reach"].pos.copy(), self.rot
            hand = self.x
            far = np.linalg.norm(hand[:2] - target[:2]) > 0.03
            if far:  # up first, then across: over the container if it is in the way
                if self.over_container(hand, target):
                    target[2] = max(target[2], wps["carry"].pos[2])
                if hand[2] < target[2] - 0.02:
                    target[:2] = hand[:2]
            elif self.settled >= round(SETTLE * FPS) and self.still() and not self.fresh_grip:
                self.locked = self.best.copy()
                self.next_step("reach")
                return self.decide()
        elif step == "descend":
            if self.obj is not None and np.linalg.norm(self.obj[:2] - self.locked[:2]) > MOVED:
                self.say("it moved: re-aiming")
                self.locked = None
                self.goto("reach")
                return self.decide()
            target, rot, speed = self.waypoints()["descend"].pos, self.rot, 0.4
            if self.arrived(target, rot):
                self.next_step()
                return self.decide()
        elif step == "close":
            self.closed = True
            target, rot = self.waypoints()["descend"].pos, self.rot
            if self.since >= round(0.6 * FPS):
                self.grasp_xy = self.x[:2].copy()
                self.next_step()
                return self.decide()
        elif step == "lift":
            target, rot, speed = self.waypoints()["lift"].pos.copy(), self.rot, 0.5
            target[:2] = self.grasp_xy
            if self.arrived(target, rot):
                self.next_step()
                return self.decide()
        elif step == "carry":
            target, rot = self.waypoints()["carry"].pos, self.rot
            if self.arrived(target, rot) and self.settled >= round(SETTLE * FPS):
                self.next_step()
                return self.decide()
        elif step == "lower":
            target, rot, speed = self.waypoints()["lower"].pos, self.rot, 0.4
            if self.arrived(target, rot):
                self.next_step()
                return self.decide()
        elif step == "open":
            self.closed = False
            target, rot = self.x.copy(), self.rot
            if self.since >= round(0.5 * FPS):
                self.release_at = self.x.copy()
                self.next_step()
                return self.decide()
        elif step == "retreat":
            height = next(s["height"] for s in self.card["steps"] if s["do"] == "retreat")
            target, rot, speed = self.release_at + [0, 0, height], self.rot, 0.5
            if self.arrived(target, rot):
                self.next_step()
                return self.decide()
        elif step == "done":
            target, rot = self.home
            if self.since > round(1.0 * FPS) and self.obj is not None and self.still() and not self.in_container():
                self.say("not in the container: starting again")
                self.recoveries += 1
                self.tries += 1
                self.fresh_grip = True
                self.goto("reach")
                return self.decide()
        self.target = target
        return target, rot, speed

    def arrived(self, target, rot):
        """Commanded hand at the target. Before closing the IK must also have settled (like the plan's last ticks, at
        most 1 s); not while holding: every extra second in a weak grip lets the object creep out."""
        here = (float(np.linalg.norm(self.x - target)) < NEAR and float(np.linalg.norm(self.v)) < 0.02
                and _rot_angle(self.R, rot) < 0.03)
        return here and (self.doing != "descend" or self.quiet >= 3 or self.settled >= FPS)

    def move(self, target, rot, speed):
        """One tick of the commanded hand: follows the target, speed and acceleration limited like the planned paths."""
        vmax = speed * 0.5 * self.scene.reach
        want = STIFF * STIFF * (target - self.x) - 2 * STIFF * self.v
        a = float(np.linalg.norm(want))
        if a > ACCEL:
            want *= ACCEL / a
        self.v = self.v + want / FPS
        v = float(np.linalg.norm(self.v))
        if v > vmax:
            self.v *= vmax / v
        self.x = self.x + self.v / FPS
        angle = _rot_angle(self.R, rot)
        if angle > 1e-3:
            self.R = _slerp(self.R, rot, min(1.0, 1.5 * speed / FPS / angle))
        self.dist = float(np.linalg.norm(self.x - target))
        if self.since == 0:
            self.d0 = self.dist
        self.settled = self.settled + 1 if self.dist < NEAR and _rot_angle(self.R, rot) < 0.03 else 0

    def step(self):
        """One 25 Hz tick: look, decide, one IK step, physics."""
        t0 = time.perf_counter()
        s = self.scene
        m, d = s.model, s.data
        if self.n % self.look_every == 0:
            self.look()
        t1 = time.perf_counter()
        target, rot, speed = self.decide()
        self.target = target
        self.move(target, rot, speed)
        if self.can_trim and float(np.linalg.norm(self.v)) < 0.05 and self.doing not in ("close", "open"):
            self.trim = np.clip(self.trim + TRIM * (self.x - s.ee_pos()), -TRIM_MAX, TRIM_MAX)
        q, _, _ = self.ik.solve(self.x + self.trim, self.R, 1 / FPS)
        self.quiet = self.quiet + 1 if self.q is not None and np.abs(q - self.q).max() < 1e-3 else 0
        self.q = q
        t2 = time.perf_counter()
        d.ctrl[self.acts] = q
        self.grip = float(np.clip(self.grip + (1 if self.closed else -1) / (GRIP_TIME * FPS), 0.0, 1.0))
        s.set_grip(self.grip)
        for _ in range(self.physics):
            mujoco.mj_step(m, d)
        t3 = time.perf_counter()
        self.n += 1
        self.since += 1
        self.ms["look"].append((t1 - t0) * 1000)
        self.ms["ik"].append((t2 - t1) * 1000)
        self.ms["physics"].append((t3 - t2) * 1000)
        self.ms["tick"].append((t3 - t0) * 1000)

    def move_object(self, xy, drop=0.0):
        """A person puts the object at `xy`. The loop finds out from its cameras, like anything else."""
        put(self.scene, xy, drop)
        self.say("object moved")

    def knock(self, lo=0.05, hi=0.30):
        """With a stick: a real hit (out of the gripper if it is held, else along the table). Without: the object
        lands on a free spot lo..hi m off, which is a teleport."""
        if self.stick:
            held = self.closed and self.touching()
            hit = self.stick.out_of_hand(self.rng) if held else self.stick.on_table(self.rng)
            if hit:
                self.say("hit with a stick")
            return hit
        xy = free_spot(self.scene, self.rng, self.scene.cube_pos()[:2], lo, hi)
        if xy is None:
            return False
        put(self.scene, xy, 0.02)
        self.say("object moved")
        return True

    def state(self):
        s = self.scene
        return {"t": round(self.n / FPS, 2), "step": self.doing, "held": bool(self.touching() and self.closed),
                "tries": self.tries, "recoveries": self.recoveries, "success": bool(self.doing == "done" and self.in_container()),
                "object": None if self.obj is None else [round(float(v), 4) for v in self.obj],
                "container": None if self.bowl is None else [round(float(v), 4) for v in self.bowl],
                "eyes": "cameras" if self.eyes else "true pose", "last": self.events[-1][1] if self.events else ""}

    def rates(self):
        """Mean ms per tick; `look` over the ticks that looked."""
        looks = [v for i, v in enumerate(self.ms["look"]) if i % self.look_every == 0]
        return {"tick": round(float(np.mean(self.ms["tick"])), 1), "look": round(float(np.mean(looks)), 1),
                "ik": round(float(np.mean(self.ms["ik"])), 1), "physics": round(float(np.mean(self.ms["physics"])), 1)}

    def run(self, seconds=60.0, on_tick=None, hold=1.0, keep_going=None):
        """Until the card's test has held for `hold` seconds at the end of the steps, or time is up."""
        good = 0
        while self.n < seconds * FPS:
            self.step()
            if on_tick:
                on_tick(self)
            good = good + 1 if self.doing == "done" and self.scene.cube_in_bowl() else 0
            if good >= hold * FPS and not (keep_going and keep_going()):
                break
        ok = self.scene.cube_in_bowl()
        return ok, "ok" if ok else f"timeout in {self.doing}"

    def close(self):
        mujoco.set_mjcb_control(None)
        if self.eyes:
            self.eyes.close()
