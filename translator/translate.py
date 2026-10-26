"""Skill card + robot adapter -> gripper waypoints in the world frame.

The card says WHAT happens (objects, grip, steps, success test). The adapter says how
this robot's gripper is built. Heights come from the object sizes, never from a demo motion.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .scene import TABLE_TOP, Scene

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


def load_card(path):
    return json.loads(Path(path).read_text())


def _axis(spec: str):
    return (1.0 if spec[0] == "+" else -1.0), "xyz".index(spec[1])


def grip_rotation(robot, closing_angle: float):
    """Rotation of the end-effector site: approach axis straight down, closing axis at the given yaw."""
    sa, ia = _axis(robot.approach_axis)
    sc, ic = _axis(robot.closing_axis)
    rot = np.zeros((3, 3))
    rot[:, ia] = sa * np.array([0.0, 0.0, -1.0])
    rot[:, ic] = sc * np.array([math.cos(closing_angle), math.sin(closing_angle), 0.0])
    k = 3 - ia - ic
    rot[:, k] = np.cross(rot[:, (k + 1) % 3], rot[:, (k + 2) % 3])
    return rot


def _rot_angle(a, b):
    return math.acos(np.clip((np.trace(a.T @ b) - 1) / 2, -1.0, 1.0))


def grip_options(robot, object_yaw: float, current_rot):
    """The four face-pair grips, the one needing the least wrist turn first."""
    options = [grip_rotation(robot, object_yaw + k * math.pi / 2) for k in range(4)]
    return sorted(options, key=lambda r: _rot_angle(r, current_rot))


def translate(card, scene: Scene, seen, check=None):
    """`seen` maps each card object to the pose the robot believes it has: {"pos": xyz, "yaw": rad}.
    `check(waypoints)` returns how far this body misses them (m); the reachable grip with the least wrist turn wins."""
    grip = card["grip"]
    options = grip_options(scene.robot, seen[grip["object"]]["yaw"], scene.ee_rot())
    if check is None:
        return _waypoints(card, scene, seen, options[0])
    plans = [_waypoints(card, scene, seen, rot) for rot in options]
    misses = [check(wps) for wps in plans]
    best = min(misses)
    return next(wps for wps, miss in zip(plans, misses) if miss < best + 0.002)


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
    offset = np.array(scene.robot.grip_offset)
    for wp in wps:
        if wp.pos is not None:
            wp.pos = wp.pos - wp.rot @ offset
    return wps
