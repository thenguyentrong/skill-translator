"""What a robot's model file says, in a short form a language model can read, plus measurements of an adapter.

facts(): joints, actuators, sites, bodies and keyframes of an MJCF file.
measure(): loads a robot with a proposed adapter and measures what the adapter claims (where the hand points,
which way the fingers close, how wide the gripper opens, where the hand is at home), so a wrong guess shows up as a
number instead of as a failed grasp.
"""
import math

import mujoco
import numpy as np

from .robots import ASSETS, from_dict
from .scene import PREFIX, TABLE_TOP, _axis_vec, build

_JTYPE = {0: "free", 1: "ball", 2: "slide", 3: "hinge"}
_TRN = {0: "joint", 1: "joint", 2: "slidercrank", 3: "tendon", 4: "site", 5: "body"}


def facts(xml):
    m = mujoco.MjModel.from_xml_path(str(xml))
    name = lambda kind, i: mujoco.mj_id2name(m, kind, i) or f"#{i}"
    joints = [{"name": name(mujoco.mjtObj.mjOBJ_JOINT, j), "type": _JTYPE[int(m.jnt_type[j])],
               "body": name(mujoco.mjtObj.mjOBJ_BODY, m.jnt_bodyid[j]),
               "range": [round(float(v), 4) for v in m.jnt_range[j]] if m.jnt_limited[j] else None}
              for j in range(m.njnt)]
    actuators = []
    for a in range(m.nu):
        kind = _TRN[int(m.actuator_trntype[a])]
        obj = {"joint": mujoco.mjtObj.mjOBJ_JOINT, "tendon": mujoco.mjtObj.mjOBJ_TENDON,
               "site": mujoco.mjtObj.mjOBJ_SITE, "body": mujoco.mjtObj.mjOBJ_BODY}.get(kind)
        target = name(obj, m.actuator_trnid[a, 0]) if obj else "?"
        actuators.append({"name": name(mujoco.mjtObj.mjOBJ_ACTUATOR, a), "drives": f"{kind} {target}",
                          "ctrlrange": [round(float(v), 4) for v in m.actuator_ctrlrange[a]] if m.actuator_ctrllimited[a] else None})
    tendons = {}
    for t in range(m.ntendon):
        tendons[name(mujoco.mjtObj.mjOBJ_TENDON, t)] = [
            name(mujoco.mjtObj.mjOBJ_JOINT, m.wrap_objid[w]) for w in range(m.tendon_adr[t], m.tendon_adr[t] + m.tendon_num[t])
            if m.wrap_type[w] == int(mujoco.mjtWrap.mjWRAP_JOINT)]
    bodies = [{"name": name(mujoco.mjtObj.mjOBJ_BODY, b), "parent": name(mujoco.mjtObj.mjOBJ_BODY, m.body_parentid[b])}
              for b in range(1, m.nbody)]
    sites = [{"name": name(mujoco.mjtObj.mjOBJ_SITE, s), "body": name(mujoco.mjtObj.mjOBJ_BODY, m.site_bodyid[s])}
             for s in range(m.nsite)]
    keys = [name(mujoco.mjtObj.mjOBJ_KEY, k) for k in range(m.nkey)]
    return {"file": str(xml.relative_to(ASSETS)) if xml.is_relative_to(ASSETS) else str(xml),
            "joints": joints, "actuators": actuators, "tendons": tendons, "bodies": bodies, "sites": sites,
            "keyframes": keys, "mass_kg": round(float(m.body_subtreemass[0]), 2)}


def _site_frame(scene, d):
    r = scene.robot
    rot = d.site_xmat[scene.ee_site_id].reshape(3, 3)
    return d.site_xpos[scene.ee_site_id] + rot @ np.array(r.grip_offset), rot


def _settled(scene, grip, steps=300):
    m = scene.model
    d = mujoco.MjData(m)
    mujoco.mj_copyData(d, m, scene.data)
    opened, shut = scene.open_ctrl, np.atleast_1d(scene.robot.gripper_closed)
    d.ctrl[scene.gripper_ids] = opened + grip * (shut - opened)
    for _ in range(steps):
        mujoco.mj_step(m, d)
    return d


def _gname(m, g):
    return m.geom(g).name or f"{m.body(m.geom_bodyid[g]).name} geom {g}"


def touches_table(scene):
    """Robot parts, other than the base it stands on, that touch or cut into the table at home."""
    m, d = scene.model, scene.data
    table = {g for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name == "table"}
    hits = set()
    for g1, g2 in zip(d.contact.geom1[:d.ncon], d.contact.geom2[:d.ncon]):
        other = g2 if g1 in table else g1 if g2 in table else None
        if other is None:
            continue
        b = m.geom_bodyid[other]
        if m.body(b).name.startswith(PREFIX) and m.body_parentid[b] != 0:
            hits.add(m.body(b).name[len(PREFIX):])
    return sorted(hits)


def _hand_blocked_by(scene, d):
    """Robot parts outside the hand that the hand touches (e.g. fingers hitting the wrist when they close)."""
    m = scene.model
    hand = set(scene._hand_geoms())
    hits = set()
    for g1, g2 in zip(d.contact.geom1[:d.ncon], d.contact.geom2[:d.ncon]):
        if (g1 in hand) != (g2 in hand):
            inside, other = (g1, g2) if g1 in hand else (g2, g1)
            if m.body(m.geom_bodyid[other]).name.startswith(PREFIX):
                hits.add(f"{_gname(m, inside)} touches {_gname(m, other)}")
    return sorted(hits)[:8]


def _placement(scene):
    """Where the robot ends up in the world at its home pose (floor z = 0, table top z = 0.75)."""
    m, d = scene.model, scene._home_data()
    robot = [g for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name.startswith(PREFIX) and m.geom_contype[g]]
    lo = min(float(d.geom_xpos[g][2] - np.abs(d.geom_xmat[g].reshape(3, 3)) @ m.geom_aabb[g, 3:] @ [0, 0, 1]
                   + (d.geom_xmat[g].reshape(3, 3) @ m.geom_aabb[g, :3])[2]) for g in robot) if robot else 0.0
    hi = max(float(d.geom_xpos[g][2] + np.abs(d.geom_xmat[g].reshape(3, 3)) @ m.geom_aabb[g, 3:] @ [0, 0, 1]
                   + (d.geom_xmat[g].reshape(3, 3) @ m.geom_aabb[g, :3])[2]) for g in robot) if robot else 0.0
    root = [b for b in range(m.nbody) if m.body_parentid[b] == 0 and m.body(b).name.startswith(PREFIX)]
    return {"world_z_of_robot_lowest_point_m": round(lo, 3), "world_z_of_robot_highest_point_m": round(hi, 3),
            "world_z_of_root_body_m": round(float(d.xpos[root[0]][2]), 3) if root else None,
            "world_z_of_arm_first_joint_m": round(float(scene.origin[2]), 3)}


def measure(adapter):
    """Numbers that test an adapter's claims. Returns (measurements, scene or None)."""
    try:
        robot = from_dict(adapter)
        scene = build(robot)
    except Exception as e:
        return {"loads": False, "error": f"{type(e).__name__}: {e}"[:600]}, None
    m = scene.model
    out = {"loads": True, "problems": scene.problems, **_placement(scene),
           "reach_at_table_m": round(scene.reach, 3), "arm_actuators": len(scene.arm_actuators),
           "arm_joints": [m.joint(j).name[len(PREFIX):] for j in scene.arm_joints]}
    if scene.ee_site_id is None:
        out["error"] = "no grip site"
        return out, scene
    d_open, d_shut = _settled(scene, 0.0), _settled(scene, 1.0)
    point, rot = _site_frame(scene, d_open)
    geoms = scene._hand_geoms()
    names = "xyz"
    # where the hand's mass of geometry lies, in the grip site's own axes
    centres = np.array([rot.T @ (d_open.geom_xpos[g] - point) for g in geoms]) if geoms else np.zeros((1, 3))
    out["hand_geometry_centre_in_site_axes_mm"] = {names[i]: round(float(centres[:, i].mean()) * 1000, 1) for i in range(3)}
    a = _axis_vec(scene.robot.approach_axis)
    out["fingers_stick_out_past_grip_point_along_approach_mm"] = round(scene.measure_tip_reach() * 1000, 1)
    # which way the fingers move when the gripper closes
    p2, rot2 = _site_frame(scene, d_shut)
    move = np.array([rot2.T @ (d_shut.geom_xpos[g] - p2) - rot.T @ (d_open.geom_xpos[g] - point) for g in geoms])
    if len(move):
        spread = np.abs(move).max(axis=0)
        out["finger_travel_when_closing_mm"] = {names[i]: round(float(spread[i]) * 1000, 1) for i in range(3)}
        side = np.array([rot.T @ (d_open.geom_xpos[g] - point) for g in geoms])
        out["open_hand_width_along_axes_mm"] = {names[i]: round(float(np.ptp(side[:, i])) * 1000, 1) for i in range(3)}
    out["hand_touches_robot_when_open"] = _hand_blocked_by(scene, d_open)
    out["hand_touches_robot_when_closed"] = _hand_blocked_by(scene, d_shut)
    if len(scene.gripper_ids) == 1:
        out["gap_at_grip_point_open_mm"] = round(scene.gripper_gap(float(scene.open_ctrl[0])) * 1000, 1)
        out["gap_at_grip_point_closed_mm"] = round(scene.gripper_gap(float(np.atleast_1d(scene.robot.gripper_closed)[0])) * 1000, 1)
    home = scene.ee_pos() - scene.origin
    out["hand_at_home_from_arm_origin_m"] = [round(float(v), 3) for v in home]
    out["hand_at_home_heading_deg"] = round(math.degrees(math.atan2(home[1], home[0])), 1)
    out["approach_axis_at_home_world"] = [round(float(v), 2) for v in scene.ee_rot() @ a]
    out["arm_origin_height_above_table_m"] = round(float(scene.origin[2] - TABLE_TOP), 3)
    out["grip_point_height_above_table_at_home_m"] = round(float(scene.ee_pos()[2] - TABLE_TOP), 3)
    out["robot_parts_touching_table_at_home"] = touches_table(scene)
    return out, scene
