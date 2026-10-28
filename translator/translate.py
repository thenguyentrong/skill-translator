"""Skill card + robot adapter -> gripper waypoints in the world frame.

The card says WHAT happens (objects, grip, steps, success test). The adapter says how
this robot's gripper is built. Heights come from the object sizes, never from a demo motion.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .scene import TABLE_TOP, Scene, rot_z

MARGIN = 0.02
SETTLE = 0.3


@dataclass
class Waypoint:
    label: str
    pos: np.ndarray | None
    rot: np.ndarray | None
    closed: bool
    speed: float = 1.0
    dwell: float = 0.0
    joint_move: bool = False
    free_turn: bool = False


def load_card(path):
    return json.loads(Path(path).read_text())


def _axis(spec: str):
    return (1.0 if spec[0] == "+" else -1.0), "xyz".index(spec[1])


def grip_rotation(robot, closing_angle: float):
    """Rotation of the end-effector site: approach axis straight down, closing axis at the given yaw."""
    return hand_rotation(robot, np.array([0.0, 0.0, -1.0]), np.array([math.cos(closing_angle), math.sin(closing_angle), 0.0]))


def hand_rotation(robot, approach, closing):
    """Rotation of the end-effector site that points its approach axis and closing axis along the given world vectors."""
    sa, ia = _axis(robot.approach_axis)
    sc, ic = _axis(robot.closing_axis)
    rot = np.zeros((3, 3))
    rot[:, ia] = sa * approach
    rot[:, ic] = sc * closing
    k = 3 - ia - ic
    rot[:, k] = np.cross(rot[:, (k + 1) % 3], rot[:, (k + 2) % 3])
    return rot


def _rot_angle(a, b):
    return math.acos(np.clip((np.trace(a.T @ b) - 1) / 2, -1.0, 1.0))


def grip_options(robot, object_yaw: float, current_rot, size=None, width=None):
    """The face-pair grips, the one needing the least wrist turn first. For a box whose sides differ, only the
    grips that close across the card's grip width (k even: across size[0], k odd: across size[1])."""
    ks = range(4)
    if size is not None and width is not None and abs(size[0] - size[1]) > 0.005:
        across_x = abs(size[0] - width) <= abs(size[1] - width)
        ks = [k for k in ks if (k % 2 == 0) == across_x]
    options = [grip_rotation(robot, object_yaw + k * math.pi / 2) for k in ks]
    return sorted(options, key=lambda r: _rot_angle(r, current_rot))


def translate(card, scene: Scene, seen, check=None):
    """`seen` maps each card object to the pose the robot believes it has: {"pos": xyz, "yaw": rad}.
    `check(waypoints)` returns how far this body misses them (m); the reachable grip with the least wrist turn wins."""
    if card.get("kind") == "open":
        tried = []
        for free in (False, True):
            plans = sorted((_open_waypoints(card, scene, seen, flip, free) for flip in (1.0, -1.0)),
                           key=lambda wps: _rot_angle(wps[0].rot, scene.ee_rot()))
            if check is None:
                return plans[0]
            tried += [(check(wps), wps) for wps in plans]
            best = min(m for m, _ in tried)
            if best < 0.01:
                break
        return next(wps for miss, wps in tried if miss < best + 0.002)
    grip = card["grip"]
    held = card["objects"][grip["object"]]
    size = held["size"] if held["shape"] == "box" else None
    options = grip_options(scene.robot, seen[grip["object"]]["yaw"], scene.ee_rot(), size, grip.get("width"))
    if check is None:
        return _waypoints(card, scene, seen, options[0])
    plans = [_waypoints(card, scene, seen, rot) for rot in options]
    misses = [check(wps) for wps in plans]
    best = min(misses)
    return next(wps for wps, miss in zip(plans, misses) if miss < best + 0.002)


def hold_depth(scene: Scene, held_half):
    """How far below the object's centre the grip point goes: the practised depth, but never so deep that
    the fingertips touch the table (3 mm to spare). For a handle: the door instead of the table."""
    return min(scene.grip_depth, held_half - scene.tip_reach - 0.003)


def _to_site(scene: Scene, wps, depth, width):
    """Grip-point targets -> end-effector site targets (grip offset, practised depth, fixed jaw)."""
    offset = np.array(scene.robot.grip_offset, dtype=float)
    sa, ia = _axis(scene.robot.approach_axis)
    offset[ia] -= sa * depth
    if scene.robot.fixed_jaw:
        sign, index = _axis(scene.robot.closing_axis)
        offset[index] += sign * (width / 2 + 0.003)
    for wp in wps:
        if wp.pos is not None:
            wp.pos = wp.pos - wp.rot @ offset
    return wps


def _open_waypoints(card, scene: Scene, seen, flip, free=False, step=math.radians(10)):
    """Open a hinged door by its bar handle: from in front of the handle, close around it, then pull along the
    circle around the hinge while the hand turns with the door. The hinge is on the side away from the handle.
    `free`: the hand may also turn about the bar instead (for arms that cannot turn with the door)."""
    cab, handle = card["success"]["object"], card["grip"]["object"]
    c, h = card["objects"][cab], card["objects"][handle]
    yaw, centre = seen[cab]["yaw"], np.asarray(seen[cab]["pos"], dtype=float)
    p0 = np.asarray(seen[handle]["pos"], dtype=float)
    n = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    t = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    s = -math.copysign(1.0, np.dot(p0 - centre, t))
    hinge = centre + n * c["size"][1] / 2 + t * s * c["size"][0] / 2
    hinge[2] = p0[2]
    end = min(math.radians(card["success"]["min_angle_deg"] + 15), math.radians(100))

    def pose(a):
        r = rot_z(s * a)
        return hinge + r @ (p0 - hinge), r @ n, hand_rotation(scene.robot, -(r @ n), flip * (r @ t))

    p, nn, rot = pose(0.0)
    wps = [Waypoint("reach", p + 0.10 * nn + [0, 0, 0.12], rot, False, speed=0.6, joint_move=True),
           Waypoint("reach", p + 0.10 * nn, rot, False, speed=0.6, dwell=1.0),
           Waypoint("approach", p, rot, False, speed=0.4, dwell=0.4)]
    for st in card["steps"]:
        do = st["do"]
        if do == "close":
            wps.append(Waypoint("close", None, None, True, dwell=0.6))
        elif do == "pull":
            k = math.ceil(end / step)
            for a in np.linspace(end / k, end, k):
                p, nn, rot = pose(a)
                wps.append(Waypoint("pull", p, rot, True, speed=0.3, free_turn=free))
        elif do == "open":
            wps.append(Waypoint("open", None, None, False, dwell=0.5))
        elif do == "retreat":
            wps.append(Waypoint("retreat", p + st.get("distance", 0.08) * nn, rot, False, speed=0.5, free_turn=free))
        elif do not in ("reach", "approach"):
            raise ValueError(f"unknown step {do!r} for an open card")
    return _to_site(scene, wps, hold_depth(scene, h["standoff"]), card["grip"]["width"])


def _waypoints(card, scene: Scene, seen, rot):
    objects = card["objects"]
    grip = card["grip"]
    held = objects[grip["object"]]
    held_half = held["size"][2] / 2
    obj_pos = seen[grip["object"]]["pos"]
    grasp_z = TABLE_TOP + held_half

    wps, z = [], grasp_z
    for step in card["steps"]:
        do = step["do"]
        if do == "reach":
            z = grasp_z + 0.10
            wps.append(Waypoint("reach", np.array([obj_pos[0], obj_pos[1], z]), rot, False, dwell=SETTLE))
        elif do == "descend":
            z = grasp_z
            wps.append(Waypoint("descend", np.array([obj_pos[0], obj_pos[1], z]), rot, False, speed=0.4))
        elif do == "close":
            wps.append(Waypoint("close", None, None, True, dwell=0.6))
        elif do == "lift":
            z = grasp_z + step["height"]
            wps.append(Waypoint("lift", np.array([obj_pos[0], obj_pos[1], z]), rot, True, speed=0.5))
        elif do == "carry":
            target = objects[step["object"]]
            bowl = seen[step["object"]]["pos"]
            z = max(z, TABLE_TOP + target["wall_height"] + held_half + 2 * MARGIN)
            wps.append(Waypoint("carry", np.array([bowl[0], bowl[1], z]), rot, True, dwell=SETTLE))
        elif do == "lower":
            container = objects[step["into"]]
            bowl = seen[step["into"]]["pos"]
            z = TABLE_TOP + container["wall_height"] + held_half + MARGIN
            wps.append(Waypoint("lower", np.array([bowl[0], bowl[1], z]), rot, True, speed=0.4))
        elif do == "open":
            wps.append(Waypoint("open", None, None, False, dwell=0.5))
        elif do == "retreat":
            last = next(w.pos for w in reversed(wps) if w.pos is not None)
            wps.append(Waypoint("retreat", last + [0, 0, step["height"]], rot, False, speed=0.5))
        else:
            raise ValueError(f"unknown step {do!r}")
    return _to_site(scene, wps, hold_depth(scene, held_half), grip.get("width", held["size"][0]))
