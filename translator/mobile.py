"""A humanoid's base that slides: its root body is welded to a target the plan moves (back off, turn, go, turn, step in).

This is option A: the legs hold their stand pose and do not step. A real humanoid walks with its maker's own
walking controller; the translator only says where the base goes."""
import math

import mujoco
import numpy as np

TARGET = "base_target"
SPEED, TURN = 0.35, 0.4


def quat_yaw(a):
    return np.array([math.cos(a / 2), 0.0, 0.0, math.sin(a / 2)])


def add_base(spec, pos, yaw, root):
    """Weld the robot's root body (full name) to a mocap target at `pos`, turned `yaw`. The weld keeps the pose the
    root has in the model's reference pose, so the target sits where the root is."""
    tgt = spec.worldbody.add_body(name=TARGET, mocap=True, pos=list(pos), quat=quat_yaw(yaw).tolist())
    tgt.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.01, 0, 0], contype=0, conaffinity=0, rgba=[0, 0, 0, 0])
    eq = spec.add_equality(type=mujoco.mjtEq.mjEQ_WELD, name1=TARGET, name2=root, objtype=mujoco.mjtObj.mjOBJ_BODY)
    eq.solref = [0.005, 1.0]
    return tgt


def sag(model, data, root_qadr, settle=0.4):
    """How far (m) the welded root sinks under the robot's weight; the base is lifted by this so the feet end up at
    floor level (contacts between robot and floor are off while the base slides)."""
    z0 = data.qpos[root_qadr + 2]
    for _ in range(round(settle / model.opt.timestep)):
        mujoco.mj_step(model, data)
    return float(z0 - data.qpos[root_qadr + 2])


def pose(data, mocap=0):
    """(x, y, yaw) of the base target."""
    w, _, _, z = data.mocap_quat[mocap]
    return float(data.mocap_pos[mocap][0]), float(data.mocap_pos[mocap][1]), 2 * math.atan2(z, w)


def path_to(start, goal, back=0.40):
    """Base poses from `start` to `goal` ((x, y, yaw) each): back off from the table, turn towards the goal, go,
    turn to the goal's heading, step in. Short moves (< 30 cm) slide straight there."""
    sx, sy, sa = start
    gx, gy, ga = goal
    if math.hypot(gx - sx, gy - sy) < 0.30:
        return [goal]
    out_s = np.array([sx, sy]) - back * np.array([math.cos(sa), math.sin(sa)])
    out_g = np.array([gx, gy]) - back * np.array([math.cos(ga), math.sin(ga)])
    head = math.atan2(out_g[1] - out_s[1], out_g[0] - out_s[0])
    return [(out_s[0], out_s[1], sa), (out_s[0], out_s[1], head), (out_g[0], out_g[1], head), (out_g[0], out_g[1], ga), goal]


def segment_seconds(a, b):
    """Time for one base move: walking speed, turning speed, at least 0.5 s, and 1.6x slack for min-jerk."""
    return max(math.hypot(b[0] - a[0], b[1] - a[1]) / SPEED, abs(b[2] - a[2]) / TURN, 0.5) * 1.6
