"""Carry: pick a crate or a basket up by its handles, take it to another table, put it down on the mark.

Two side handles take two hands; one top handle takes one. A humanoid's base slides between the tables
(mobile.py: the legs do not step). An arm on a fixed base can only carry when both places are inside its reach.
Each hand grips its handle from above, palm down, closing across the bar, 1 cm below the bar's centre by default
(practice finds each robot's depth): at the centre the bar squeezes out of a pinch, 2 cm lower the fingers hit the rim."""
import math
from dataclasses import dataclass
from types import SimpleNamespace

import mujoco
import numpy as np

from . import mobile
from .execute import FPS, IK_FAIL, Result, _min_jerk
from .ik import HandsIK
from .scene import PREFIX, TABLE_TOP, rot_z
from .translate import hand_rotation

TABLE_B = (0.10, 0.30, 0.45)  # second table: centre x, half size x, half size y (its near edge lines up with table A)
WALL = 0.008
LIFT, PRE, WITHIN_REACH_FAR = 0.13, 0.06, 0.75
DEPTH = 0.01


def objects(card):
    """What the scene needs from a carry card."""
    crate, place = card["grip"]["object"], card["success"]["place"]
    c, p = card["objects"][crate], card["objects"][place]
    side = -1.0 if p.get("side") == "right" else 1.0
    return {"kind": "carry", "held": crate, "held_shape": "crate", "held_size": np.array(c["size"], dtype=float),
            "container": place, "container_shape": "place", "bowl_radius": float(card["success"].get("within", 0.10)),
            "bowl_wall": 0.0, "handles": c["handles"], "handle": c["handle"], "mass": float(c["mass"]),
            "move": side * float(p["distance"])}


def has_table_b(objs):
    return abs(objs["move"]) >= 0.6 + TABLE_B[2] + 0.05


def add(spec, objs):
    """The crate (red walls, grey handles, origin at the middle of its bottom), the green mark where it must end up,
    and a second table when the mark is too far for the first."""
    world = spec.worldbody
    w, l, h = objs["held_size"]
    mass, hd = objs["mass"], objs["handle"]
    red, grey = [0.85, 0.2, 0.15, 1], [0.3, 0.3, 0.33, 1]
    body = world.add_body(name="cube", pos=[0.4, 0.2, TABLE_TOP + 0.001])
    body.add_freejoint(name="cube")
    parts = [([w / 2, l / 2, WALL / 2], [0, 0, WALL / 2])]
    parts += [([WALL / 2, l / 2, h / 2], [s * (w / 2 - WALL / 2), 0, h / 2]) for s in (-1, 1)]
    parts += [([w / 2, WALL / 2, h / 2], [0, s * (l / 2 - WALL / 2), h / 2]) for s in (-1, 1)]
    for size, pos in parts:
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=size, pos=pos, mass=mass * 0.9 / len(parts), rgba=red,
                      friction=[1.0, 0.005, 0.002], condim=6, contype=3, conaffinity=3)
    r = hd["diameter"] / 2
    bar = dict(type=mujoco.mjtGeom.mjGEOM_CAPSULE, size=[r, 0, 0], mass=mass * 0.05, rgba=grey,
               friction=[1.0, 0.005, 0.002], condim=6)
    if objs["handles"] == "top":
        top = hd["height"]
        body.add_geom(name="handle_0", fromto=[0, -hd["length"] / 2, top, 0, hd["length"] / 2, top], **bar)
        for s in (-1, 1):
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, size=[0.008, 0, 0], mass=mass * 0.025, rgba=grey,
                          fromto=[0, s * hd["length"] / 2, top, 0, s * (l / 2 - WALL / 2), h - 0.005])
    elif objs["handles"] == "side":
        for i, s in enumerate((-1, 1)):
            body.add_geom(name=f"handle_{i}", fromto=[0, s * l / 2, hd["height"], 0, s * (l / 2 + hd["length"]), hd["height"]], **bar)
    mark = world.add_body(name="bowl", pos=[0.4, -0.2, TABLE_TOP + 0.0005])
    mark.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[objs["bowl_radius"], 0.0005, 0], contype=0, conaffinity=0,
                  rgba=[0.25, 0.62, 0.35, 0.6])
    if has_table_b(objs):
        x, hx, hy = TABLE_B
        t = world.add_body(name="table_b", pos=[x, objs["move"], TABLE_TOP])
        t.add_geom(name="table_b_top", type=mujoco.mjtGeom.mjGEOM_BOX, size=[hx, hy, 0.02], pos=[0, 0, -0.02],
                   rgba=[0.55, 0.52, 0.45, 1])
        for sx in (-1, 1):
            for sy in (-1, 1):
                t.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.025, 0.025, (TABLE_TOP - 0.04) / 2],
                           pos=[sx * (hx - 0.05), sy * (hy - 0.05), -0.04 - (TABLE_TOP - 0.04) / 2], rgba=[0.45, 0.36, 0.27, 1])


def floor_off(model):
    """Robot-floor contacts off while the base slides (knees touching the floor dragged the robot); objects keep
    theirs (floor and crate are on contact bit 2, the robot loses it)."""
    for g in range(model.ngeom):
        if model.body(model.geom_bodyid[g]).name.startswith(PREFIX):
            model.geom_contype[g] &= ~2
            model.geom_conaffinity[g] &= ~2


def on_place(objs, xy, margin):
    """True when `xy` is on the table that holds the mark (table B, or table A when the mark is close)."""
    if has_table_b(objs):
        x, hx, hy = TABLE_B
        return abs(xy[0] - x) < hx - margin and abs(xy[1] - objs["move"]) < hy - margin
    from .scene import TABLE_CENTRE, TABLE_HALF
    return all(abs(xy[i] - TABLE_CENTRE[i]) < TABLE_HALF[i] - margin for i in range(2))


def reach_out(objs):
    """How far the crate (with its handles) reaches from its centre."""
    w, l, _ = objs["held_size"]
    out = objs["handle"]["length"] if objs["handles"] == "side" else 0.0
    return math.hypot(w / 2, l / 2 + out)


def sample(scene, rng, draws=2000):
    """Crate on table A, the mark `move` metres to its side. A humanoid walks to the crate, so it only has to be in
    front of it; an arm needs crate and mark inside its reach (35-75 %)."""
    o = scene.objs
    half = reach_out(o)
    for _ in range(draws):
        if scene.robot.mobile:
            if has_table_b(o):
                y = scene.base[1] + rng.uniform(-0.08, 0.08)
            else:
                lo, hi = sorted((-0.6 + half + 0.05, 0.6 - half - 0.05 - o["move"]))
                y = rng.uniform(lo, hi)
            xy = np.array([scene.base[0] + rng.uniform(0.32, 0.44), y])
        else:
            r = rng.uniform(max(0.35 * scene.reach, scene.footprint + half), WITHIN_REACH_FAR * scene.reach)
            a = rng.uniform(-math.pi / 3, math.pi / 3)
            xy = scene.origin[:2] + r * np.array([math.cos(a), math.sin(a)])
        mark = xy + [0.0, o["move"]]
        if not scene.on_table(xy, half + 0.02) or not on_place(o, mark, half + 0.02):
            continue
        if not scene.robot.mobile:
            far = WITHIN_REACH_FAR * scene.reach
            if np.linalg.norm(mark - scene.origin[:2]) > far or not scene.clear_of_robot(xy, half) or not scene.clear_of_robot(mark, half):
                continue
        return xy, mark, rng.uniform(-math.radians(10), math.radians(10))
    raise ValueError("; ".join(scene.problems) or f"no room: the crate and a mark {abs(o['move']):.1f} m to its side do "
                     f"not both fit inside the {scene.robot.name}'s reach ({scene.reach:.2f} m) and it cannot move")


def handle_points(objs, pos, yaw):
    """World centre of each handle bar (one for a top handle, two for side handles) for a crate at `pos`, `yaw`."""
    w, l, _ = objs["held_size"]
    hd, r = objs["handle"], rot_z(yaw)
    if objs["handles"] == "top":
        return [np.asarray(pos) + r @ [0.0, 0.0, hd["height"]]]
    return [np.asarray(pos) + r @ [0.0, s * (l / 2 + hd["length"] / 2), hd["height"]] for s in (-1, 1)]


@dataclass
class Hand:
    side: str
    site: int
    joints: list
    qadr: list
    acts: list
    grip: list
    open: np.ndarray
    closed: np.ndarray
    release: np.ndarray
    axes: SimpleNamespace
    sign: float


def hands_of(scene, n):
    """The hands the plan uses: the adapter's hand (right), plus its second hand (`left` in the adapter) for two."""
    m, r = scene.model, scene.robot
    joint_acts = [a for a in scene.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
    right = Hand("right", scene.ee_site_id, [int(m.actuator_trnid[a, 0]) for a in joint_acts],
                 [int(m.jnt_qposadr[m.actuator_trnid[a, 0]]) for a in joint_acts], joint_acts, list(scene.gripper_ids),
                 np.atleast_1d(r.handle_open if r.handle_open else scene.open_ctrl).astype(float), scene.close_ctrl.copy(),
                 np.atleast_1d(r.handle_release if r.handle_release else (r.handle_open or scene.open_ctrl)).astype(float),
                 SimpleNamespace(approach_axis=r.approach_axis, closing_axis=r.closing_axis), 1.0)
    if n == 1:
        return [right]
    lf = r.left
    acts = [a for a in range(m.nu) if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)
            and m.actuator(a).name[len(PREFIX):].startswith(tuple(lf["active"]))]
    left = Hand("left", m.site(PREFIX + lf["ee_site"]).id, [int(m.actuator_trnid[a, 0]) for a in acts],
                [int(m.jnt_qposadr[m.actuator_trnid[a, 0]]) for a in acts], acts, [m.actuator(PREFIX + g).id for g in lf["gripper"]],
                np.array(lf.get("handle_open", lf["gripper_open"]), dtype=float), np.array(lf["gripper_closed"], dtype=float),
                np.array(lf.get("handle_release", lf.get("handle_open", lf["gripper_open"])), dtype=float),
                SimpleNamespace(approach_axis=lf["approach_axis"], closing_axis=lf["closing_axis"]), -1.0)
    return [right, left]


def palm_down(hand, heading):
    """Hand pointing down, fingers closing along the heading (across a bar that runs sideways)."""
    return hand_rotation(hand.axes, np.array([0.0, 0.0, -1.0]), np.array([math.cos(heading), math.sin(heading), 0.0]))


class Runner:
    """Plays the plan in full physics: arm moves, grip changes and base moves; records the state 25 times a second."""

    def __init__(self, scene, on_tick=None):
        self.s, self.m, self.d = scene, scene.model, scene.data
        self.every = round(1 / FPS / self.m.opt.timestep)
        self.k, self.label, self.on_tick = 0, "start", on_tick
        self.history = [self.d.qpos.copy()]
        self.mocap = None
        if scene.robot.mobile and "base_target" in [self.m.body(b).name for b in range(self.m.nbody)]:
            self.mocap = int(self.m.body_mocapid[self.m.body(mobile.TARGET).id])

    def step(self, n=1):
        for _ in range(n):
            mujoco.mj_step(self.m, self.d)
            self.k += 1
            if self.k % self.every == 0:
                self.history.append(self.d.qpos.copy())
                if self.on_tick:
                    self.on_tick(self.label)

    def wait(self, secs):
        self.step(round(secs / self.m.opt.timestep))

    def move(self, goal, secs):
        """Min-jerk from the current commands to `goal` ({actuator: value})."""
        start = {a: float(self.d.ctrl[a]) for a in goal}
        n = max(1, round(secs / self.m.opt.timestep))
        for k in range(1, n + 1):
            s = _min_jerk(k / n)
            for a, q in goal.items():
                self.d.ctrl[a] = start[a] + s * (q - start[a])
            self.step()

    def fingers(self, hands, which, secs):
        self.move({a: float(v) for h in hands for a, v in zip(h.grip, getattr(h, which))}, secs)

    def arms(self, hands, qs, secs):
        self.move({a: float(q) for h, qh in zip(hands, qs) for a, q in zip(h.acts, qh)}, secs)

    def line(self, ik, hands, a, b, secs, n=5):
        """Straight line for every hand from targets `a` to `b`, IK at `n` points along it."""
        errs = []
        for s in np.linspace(0, 1, n + 1)[1:]:
            qs, errs = ik.solve(self.d.qpos, [(pa + s * (pb - pa), rb) for (pa, _), (pb, rb) in zip(a, b)])
            self.arms(hands, qs, secs / n)
        return errs

    def walk(self, poses):
        d = self.d
        for goal in poses:
            x, y, a = mobile.pose(d, self.mocap)
            turn = (goal[2] - a + math.pi) % (2 * math.pi) - math.pi
            p0 = d.mocap_pos[self.mocap].copy()
            n = round(mobile.segment_seconds((x, y, a), (goal[0], goal[1], a + turn)) / self.m.opt.timestep)
            for k in range(1, n + 1):
                s = _min_jerk(k / n)
                d.mocap_pos[self.mocap][:2] = p0[:2] + s * (np.array(goal[:2]) - p0[:2])
                d.mocap_quat[self.mocap] = mobile.quat_yaw(a + s * turn)
                self.step()


def _work_offsets(two):
    """Base positions to try, as (forward, sideways) of the grip point from the base: the crate centre for two
    hands, the handle in front of the right shoulder for one."""
    fwd = (0.30, 0.34, 0.37, 0.40, 0.44, 0.48)
    side = (0.0,) if two else (-0.10, -0.14, -0.17, -0.20, -0.24)
    return [(f, s) for f in fwd for s in side]


def _base_qpos(scene, qpos, base, root_qadr, rel):
    """qpos with the robot's root moved to base pose (x, y, yaw), keeping its height and its pose relative to the target."""
    q = qpos.copy()
    q[root_qadr:root_qadr + 2] = base[:2]
    out = np.zeros(4)
    mujoco.mju_mulQuat(out, mobile.quat_yaw(base[2]), rel)
    q[root_qadr + 3:root_qadr + 7] = out
    return q


def run(scene, card, seen, on_tick=None):
    """Fail labels: not_reached (a hand misses its handle by > 1 cm), handle_too_high (it cannot get above the handle
    palm down), not_lifted, dropped_while_walking, placed_badly (off the mark or tipped over)."""
    o, m, d = scene.objs, scene.model, scene.data
    crate, place = card["grip"]["object"], card["success"]["place"]
    pos, yaw = np.asarray(seen[crate]["pos"], dtype=float), float(seen[crate]["yaw"])
    mark = np.asarray(seen[place]["pos"], dtype=float)
    two = o["handles"] == "side"
    hands = hands_of(scene, 2 if two else 1)
    ik = HandsIK(scene, hands)
    go = Runner(scene, on_tick)
    go.wait(0.5)
    mob = go.mocap is not None
    face = mobile.pose(d, go.mocap)[2] if mob else 0.0
    heading = yaw if math.cos(yaw - face) >= 0 else yaw + math.pi
    fwd = np.array([math.cos(heading), math.sin(heading), 0.0])
    left = np.array([-math.sin(heading), math.cos(heading), 0.0])
    pts = sorted(handle_points(o, pos, yaw), key=lambda p: float(p @ left))
    rots = [palm_down(h, heading) for h in hands]
    depth = scene.grip_depth

    def at(points, dz):
        return [(p + [0.0, 0.0, dz], r) for p, r in zip(points, rots)]

    grip_pt = (pts[0] + pts[-1]) / 2
    if mob:
        root_qadr = int(m.jnt_qposadr[m.body_jntadr[m.body(scene.root).id]])
        rel = np.zeros(4)
        mujoco.mju_mulQuat(rel, [d.mocap_quat[go.mocap][0], *(-d.mocap_quat[go.mocap][1:])], d.qpos[root_qadr + 3:root_qadr + 7])
        key = (o["handles"], round(depth, 3))
        if key not in scene.carry_offsets:
            best = None
            for f, s in _work_offsets(two):
                base = grip_pt[:2] - f * fwd[:2] - s * left[:2]
                q = _base_qpos(scene, d.qpos, (*base, heading), root_qadr, rel)
                _, e1 = ik.solve(q, at(pts, PRE), iters=150)
                _, e2 = ik.solve(q, at(pts, -depth), iters=150)
                score = (round(max(e1 + e2), 3), abs(f - 0.37) + abs(s + (0.0 if two else 0.17)))
                if best is None or score < best[0]:
                    best = (score, (f, s), min(ik.sites_z) < pts[0][2] - depth)
            scene.carry_offsets[key] = best[1]
            if best[0][0] > IK_FAIL:  # a body limit, not bad luck: say so for every trial instead of trying
                label = "handle_too_high" if best[2] else "handle_too_low"
                scene.needs_fail = (label, f"from no base position can its hand get palm down onto the handle "
                                           f"{o['handle']['height']:.2f} m above the table: {best[0][0] * 100:.0f} cm short at best")
        if scene.needs_fail:
            return Result(False, scene.needs_fail[0], cube_at={"why": scene.needs_fail[1]})
        f, s = scene.carry_offsets[key]
        base_a = (*(grip_pt[:2] - f * fwd[:2] - s * left[:2]), heading)
        go.label = "approach"
        go.walk(mobile.path_to(mobile.pose(d, go.mocap), base_a))
        go.wait(0.3)
    ready = [(p - 0.15 * fwd - 0.05 * h.sign * left + [0.0, 0.0, PRE], r) for h, p, r in zip(hands, pts, rots)]
    go.label = "reach"
    go.fingers(hands, "open", 0.5)
    if mob:  # hands up near the body first: a straight reach from the hanging arms sweeps them through the crate
        here = mobile.pose(d, go.mocap)
        near = [(np.array([here[0], here[1], p[2] + 0.10]) + rot_z(here[2]) @ [0.12, -0.24 * h.sign, 0.0], r)
                for h, p, r in zip(hands, pts, rots)]
        qs, _ = ik.solve(d.qpos, near, iters=300)
        go.arms(hands, qs, 1.5)
    else:
        near = [(d.site_xpos[h.site].copy(), r) for h, r in zip(hands, rots)]
    go.line(ik, hands, near, ready, 1.0)
    e_pre = go.line(ik, hands, ready, at(pts, PRE), 1.5)
    high = [ik.sites_z[i] < t[0][2] - IK_FAIL for i, t in enumerate(at(pts, PRE))]
    go.label = "descend"
    e_grasp = go.line(ik, hands, at(pts, PRE), at(pts, -depth), 1.2)
    grasp_z = [float(d.site_xpos[h.site][2]) for h in hands]
    go.label = "close"
    go.fingers(hands, "closed", 0.8)
    go.wait(0.3)
    go.label = "lift"
    go.line(ik, hands, at(pts, -depth), at(pts, LIFT - depth), 1.5)
    go.wait(0.3)
    lifted = float(scene.cube_pos()[2] - TABLE_TOP)
    shift = np.array([mark[0] - pos[0], mark[1] - pos[1], 0.0])
    go.label = "walk"
    if mob:
        b = mobile.pose(d, go.mocap)
        go.walk(mobile.path_to(b, (b[0] + shift[0], b[1] + shift[1], b[2])))
    else:
        held = at(pts, LIFT - depth)
        go.line(ik, hands, held, [(p + shift, r) for p, r in held], max(1.5, np.linalg.norm(shift) / 0.15), n=8)
    go.wait(1.5)
    carried = float(scene.cube_pos()[2] - TABLE_TOP)
    go.label = "lower"
    now = [(d.site_xpos[h.site].copy(), r) for h, r in zip(hands, rots)]
    drop = max(0.0, min(float(d.site_xpos[h.site][2]) - z for h, z in zip(hands, grasp_z)) - 0.003)
    low = [(p - [0.0, 0.0, drop], r) for p, r in now]
    go.line(ik, hands, now, low, 1.8)
    go.wait(0.3)
    go.label = "open"
    go.fingers(hands, "release", 0.8)
    go.wait(0.3)
    go.label = "retreat"
    go.line(ik, hands, low, [(p + [0.0, 0.0, 0.12], r) for p, r in low], 1.2)
    if mob:
        b = mobile.pose(d, go.mocap)
        go.walk([(b[0] - 0.25 * math.cos(b[2]), b[1] - 0.25 * math.sin(b[2]), b[2])])
    go.wait(1.0)

    end = scene.cube_pos()
    up = d.xmat[m.body("cube").id].reshape(3, 3)[:, 2]
    dist = float(np.linalg.norm(end[:2] - scene.bowl_pos()[:2]))
    tilt = math.degrees(math.acos(float(np.clip(up[2], -1.0, 1.0))))
    resting = abs(end[2] - TABLE_TOP) < 0.02 and on_place(o, end[:2], 0.0)
    ok = bool(resting and dist <= o["bowl_radius"] and tilt < card["success"].get("max_tilt_deg", 10))
    if ok:
        reason = "ok"
    elif max(e_grasp) > IK_FAIL:
        reason = "handle_too_high" if any(high) else "not_reached"
    elif lifted < 0.05:
        reason = "not_lifted"
    elif carried < 0.05:
        reason = "dropped_while_walking"
    else:
        reason = "placed_badly"
    info = {"lifted_cm": round(100 * lifted, 1), "after_walk_cm": round(100 * carried, 1), "dist_cm": round(100 * dist, 1),
            "tilt_deg": round(tilt, 1), "hands": len(hands), "base_slides": mob}
    return Result(ok, reason, {"pre": max(e_pre), "grasp": max(e_grasp)}, {}, info, go.history)
