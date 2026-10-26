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
        duration = max(0.5, np.linalg.norm(wp.pos - pos) / (speed * wp.speed), _rot_angle(rot, wp.rot) / (1.5 * wp.speed))
        n = math.ceil(duration * FPS)
        for i in range(1, n + 1):
            s = _min_jerk(i / n)
            q, pe, re = ik.solve(pos + s * (wp.pos - pos), _slerp(rot, wp.rot, s), 1 / FPS)
            ticks.append((q, closed, wp.label))
        for _ in range(FPS):
            q_new, pe, re = ik.solve(wp.pos, wp.rot, 1 / FPS)
            if np.abs(q_new - q).max() < 1e-3:
                break
            q = q_new
            ticks.append((q, closed, wp.label))
        ticks += [(q, closed, wp.label)] * round(wp.dwell * FPS)
        pos_err[wp.label], rot_err[wp.label] = pe, re
        pos, rot = wp.pos, wp.rot
    return ticks, pos_err, rot_err


def run(scene: Scene, ticks, settle=1.0, on_tick=None):
    m, d = scene.model, scene.data
    acts = [a for a in scene.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
    steps = round(1 / FPS / m.opt.timestep)
    history, cube_at = [d.qpos.copy()], {}
    grip = 0.0
    for q, closed, label in ticks:
        d.ctrl[acts] = q
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
        for _ in range(4):
            _, pe, _ = ik.solve(wp.pos, wp.rot, 0.25)
        if wp.label in steps:
            miss = max(miss, pe)
    return miss


def run_skill(scene: Scene, card, seen, on_tick=None):
    waypoints = translate(card, scene, seen, check=lambda wps: reach_miss(scene, wps))
    ticks, pos_err, rot_err = plan(scene, waypoints)
    history, cube_at = run(scene, ticks, on_tick=on_tick)
    lifted = cube_at["lift"][2] - TABLE_TOP > 0.05
    held_to_bowl = cube_at["lower"][2] - TABLE_TOP > 0.04
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
