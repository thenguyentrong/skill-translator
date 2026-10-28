"""Waypoints -> smooth joint plan (IK at every control tick) -> run in full physics -> success test."""
import math
from dataclasses import dataclass, field

import mink
import mujoco
import numpy as np

from .ik import IK
from .scene import TABLE_TOP, Scene
from .translate import translate

FPS = 25
GRIP_TIME = 0.4
IK_FAIL = 0.01
CONTACT_STEPS = ("descend", "lower")


@dataclass
class Result:
    success: bool
    reason: str
    pos_err: dict = field(default_factory=dict)
    rot_err: dict = field(default_factory=dict)
    cube_at: dict = field(default_factory=dict)
    history: list = field(default_factory=list)


def _min_jerk(s):
    return 10 * s**3 - 15 * s**4 + 6 * s**5


def _slerp(r0, r1, s):
    w = (mink.SO3.from_matrix(r0).inverse() @ mink.SO3.from_matrix(r1)).log()
    return (mink.SO3.from_matrix(r0) @ mink.SO3.exp(s * w)).as_matrix()


def _rot_angle(a, b):
    return math.acos(np.clip((np.trace(a.T @ b) - 1) / 2, -1.0, 1.0))


def plan(scene: Scene, waypoints):
    ik = IK(scene)
    pos, rot = scene.ee_pos(), scene.ee_rot()
    q = ik.cfg.q[ik.arm_qadr].copy()
    closed = False
    ticks, pos_err, rot_err = [], {}, {}
    speed = 0.5 * scene.reach
    for wp in waypoints:
        if wp.pos is None:
            closed = wp.closed
            ticks += [(q, closed, wp.label)] * round(wp.dwell * FPS)
            continue
        if wp.joint_move:
            q_to, pe, re = ik.reach(wp.pos, wp.rot)
            n = math.ceil(max(0.5, np.abs(q_to - q).max() / (0.5 * scene.robot.max_joint_speed)) * FPS)
            ticks += [(q + _min_jerk(i / n) * (q_to - q), closed, wp.label) for i in range(1, n + 1)]
            ticks += [(q_to, closed, wp.label)] * round(wp.dwell * FPS)
            q, pos, rot = q_to, wp.pos, wp.rot
            pos_err[wp.label], rot_err[wp.label] = max(pe, pos_err.get(wp.label, 0.0)), max(re, rot_err.get(wp.label, 0.0))
            continue
        duration = max(0.5, np.linalg.norm(wp.pos - pos) / (speed * wp.speed), _rot_angle(rot, wp.rot) / (1.5 * wp.speed))
        n = math.ceil(duration * FPS)
        for i in range(1, n + 1):
            s = _min_jerk(i / n)
            q, pe, re = ik.solve(pos + s * (wp.pos - pos), _slerp(rot, wp.rot, s), 1 / FPS, free_turn=wp.free_turn)
            ticks.append((q, closed, wp.label))
        for _ in range(FPS):
            q_new, pe, re = ik.solve(wp.pos, wp.rot, 1 / FPS, free_turn=wp.free_turn)
            if np.abs(q_new - q).max() < 1e-3:
                break
            q = q_new
            ticks.append((q, closed, wp.label))
        ticks += [(q, closed, wp.label)] * round(wp.dwell * FPS)
        pos_err[wp.label], rot_err[wp.label] = max(pe, pos_err.get(wp.label, 0.0)), max(re, rot_err.get(wp.label, 0.0))
        pos, rot = wp.pos, wp.rot
    return ticks, pos_err, rot_err


def run(scene: Scene, ticks, settle=1.0, on_tick=None):
    m, d = scene.model, scene.data
    acts = [a for a in scene.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
    steps = round(1 / FPS / m.opt.timestep)
    history, cube_at = [d.qpos.copy()], {}
    grip = 0.0
    for q, closed, label in ticks:
        scene.command = q  # what the plan asks for; with `scene.push` set, the arm gets a little off course
        d.ctrl[acts] = q + scene.push(label) if getattr(scene, "push", None) else q
        grip = float(np.clip(grip + (1 if closed else -1) / (GRIP_TIME * FPS), 0.0, 1.0))
        scene.set_grip(grip)
        for _ in range(steps):
            mujoco.mj_step(m, d)
        history.append(d.qpos.copy())
        cube_at[label] = scene.cube_pos()
        if on_tick:
            on_tick(label)
    for _ in range(round(settle * FPS)):
        for _ in range(steps):
            mujoco.mj_step(m, d)
        history.append(d.qpos.copy())
        if on_tick:
            on_tick("settle")
    return history, cube_at


def reach_miss(scene: Scene, waypoints, steps=("descend", "lift", "carry", "lower")):
    """How far (m) the arm misses the key waypoints when it goes through them in order from home."""
    ik = IK(scene)
    miss = 0.0
    for wp in waypoints:
        if wp.pos is None:
            continue
        if wp.joint_move:
            _, pe, _ = ik.reach(wp.pos, wp.rot)
        for _ in range(4):
            _, pe, _ = ik.solve(wp.pos, wp.rot, 0.25, free_turn=wp.free_turn)
        if wp.label in steps:
            miss = max(miss, pe)
    return miss


def _run_open(scene: Scene, card, seen, on_tick=None):
    """Open card. Fail labels: not_reached (IK misses the handle or the arc by > 1 cm), missed_handle (the door
    hardly moved: the fingers closed beside the bar), slipped_off_handle (the door moved, then the hand lost the
    bar), door_not_open (still holding, but the door stopped short)."""
    waypoints = translate(card, scene, seen, check=lambda wps: reach_miss(scene, wps, ("approach", "pull")))
    ticks, pos_err, rot_err = plan(scene, waypoints)
    history, _ = run(scene, ticks, on_tick=on_tick)
    m, d = scene.model, mujoco.MjData(scene.model)
    d.qpos[:] = history[max(i for i, t in enumerate(ticks) if t[2] == "pull") + 1]
    mujoco.mj_kinematics(m, d)
    hand = d.site_xpos[scene.ee_site_id] + d.site_xmat[scene.ee_site_id].reshape(3, 3) @ np.array(scene.robot.grip_offset)
    gap = float(np.linalg.norm(hand - d.geom_xpos[scene.handle_id]))
    pulled, angle = math.degrees(d.qpos[scene.door_qadr]), math.degrees(scene.door_angle())
    success = angle >= card["success"]["min_angle_deg"]
    if success:
        reason = "ok"
    elif max(pos_err["approach"], pos_err["pull"]) > IK_FAIL:
        reason = "not_reached"
    elif pulled < 5:
        reason = "missed_handle"
    elif gap > 0.025:
        reason = "slipped_off_handle"
    else:
        reason = "door_not_open"
    return Result(success, reason, pos_err, rot_err, {"door_deg": round(angle, 1), "after_pull_deg": round(pulled, 1),
                                                      "hand_to_handle_m": round(gap, 4)}, history)


def run_skill(scene: Scene, card, seen, on_tick=None):
    if scene.refusal:
        return Result(False, scene.refusal[0], cube_at={"why": scene.refusal[1]})
    if card.get("kind") == "open":
        return _run_open(scene, card, seen, on_tick)
    if card.get("kind") == "carry":
        from . import carry
        return carry.run(scene, card, seen, on_tick)
    waypoints = translate(card, scene, seen, check=lambda wps: reach_miss(scene, wps))
    ticks, pos_err, rot_err = plan(scene, waypoints)
    history, cube_at = run(scene, ticks, on_tick=on_tick)
    rest = TABLE_TOP + scene.held_half
    lift = next(w for w in waypoints if w.label == "lift")
    lifted = cube_at["lift"][2] - rest > 0.5 * (lift.pos[2] - waypoints[1].pos[2])
    held_to_bowl = (cube_at["lower"][2] - rest > 0.006 + 0.005
                    and np.linalg.norm(cube_at["lower"][:2] - scene.bowl_pos()[:2]) < scene.container_xy + 0.02)
    success = scene.cube_in_bowl()
    if success:
        reason = "ok"
    elif max(pos_err[k] for k in CONTACT_STEPS) > IK_FAIL:
        reason = "ik"
    elif not lifted:
        reason = "grasp"
    elif not held_to_bowl:
        reason = "drop"
    else:
        reason = "bowl"
    return Result(success, reason, pos_err, rot_err, cube_at, history)
