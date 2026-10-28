"""Oli (LimX HU_D04) with LimX's own parallel grippers, as one MuJoCo model.

LimX ships MJCF only for the base robot, whose hands are fixed shapes inside the wrist mesh; the gripper version is
URDF only. This keeps the official MJCF (real ankle and waist linkages, actuators, sensors) and swaps in, from the
gripper URDF, the short wrist mesh and the gripper on both arms. The URDF mimic pairs become equality constraints,
both fingers close together, and one position actuator per side drives them (torque limit from the URDF).
Writes assets/robots/limx_humanoid/HU_D04_description/xml/HU_D04_01_gripper.xml.
"""
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DESC = ROOT / "assets" / "robots" / "limx_humanoid" / "HU_D04_description"
OUT = DESC / "xml" / "HU_D04_01_gripper.xml"


def gripper_spec():
    """Only the right gripper's links and joints from the URDF, renamed without the side (gripper_link_0 is the root);
    the left one in the URDF is the same."""
    urdf = ET.parse(DESC / "urdf" / "HU_D04_01_with_gripper.urdf").getroot()
    robot = ET.Element("robot", name="gripper")
    ET.SubElement(ET.SubElement(robot, "mujoco"), "compiler", meshdir=str((DESC / "meshes" / "HU_D04_01").resolve()),
                  fusestatic="false", discardvisual="false", strippath="true")
    joint0 = None
    for el in urdf:
        name = el.get("name", "")
        if not name.startswith("right_gripper_"):
            continue
        if el.tag == "joint" and name.endswith("_0"):
            joint0 = el.find("origin")
            continue
        el.set("name", name.replace("right_", ""))
        for tag in ("parent", "child"):
            if el.find(tag) is not None:
                el.find(tag).set("link", el.find(tag).get("link").replace("right_", ""))
        for mesh in el.iter("mesh"):
            mesh.set("filename", mesh.get("filename").split("/")[-1])
        robot.append(el)
    xyz = [float(v) for v in joint0.get("xyz").split()]
    roll, pitch, yaw = (float(v) for v in joint0.get("rpy").split())
    assert roll == 0 and yaw == 0
    return mujoco.MjSpec.from_string(ET.tostring(robot, encoding="unicode")), xyz, [math.cos(pitch / 2), 0, math.sin(pitch / 2), 0]


def main():
    spec = mujoco.MjSpec.from_file(str(DESC / "xml" / "HU_D04_01.xml"))
    effort = 1.0
    for side in ("left", "right"):
        grip, mount_pos, mount_quat = gripper_spec()  # attaching moves the bodies out of `grip`, so one per side
        wrist = spec.body(f"{side}_wrist_roll_link")
        for g in list(wrist.geoms):
            spec.delete(g)
        short = f"{side}_wrist_roll_short_link"
        spec.add_mesh(name=short, file=f"{short}.STL")
        wrist.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=short, contype=0, conaffinity=0, group=1,
                       rgba=[0.753, 0.753, 0.753, 1])
        wrist.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=short, group=3)
        wrist.add_frame(pos=mount_pos, quat=mount_quat).attach_body(grip.body("gripper_link_0"), f"{side}_", "")
        for i in range(5):
            for g in spec.body(f"{side}_gripper_link_{i}").geoms:
                if g.contype:
                    g.group = 3
                else:
                    g.rgba = [0.3, 0.3, 0.32, 1]
        j = [f"{side}_gripper_joint_{i}" for i in range(1, 5)]
        for a, b in ((j[1], j[0]), (j[3], j[2]), (j[2], j[0])):
            spec.add_equality(type=mujoco.mjtEq.mjEQ_JOINT, name1=a, name2=b, data=[0, 1, 0, 0, 0] + [0] * 7)
        act = spec.add_actuator(name=f"{side}_gripper", target=j[0], trntype=mujoco.mjtTrn.mjTRN_JOINT)
        kp = 20.0
        act.gaintype, act.gainprm[0] = mujoco.mjtGain.mjGAIN_FIXED, kp
        act.biastype = mujoco.mjtBias.mjBIAS_AFFINE
        act.biasprm[0], act.biasprm[1], act.biasprm[2] = 0.0, -kp, -kp / 10
        act.ctrllimited, act.ctrlrange = mujoco.mjtLimited.mjLIMITED_TRUE, [0.0, 1.0]
        act.forcelimited, act.forcerange = mujoco.mjtLimited.mjLIMITED_TRUE, [-effort, effort]

    m = spec.compile()
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    for side in ("left", "right"):
        base = m.body(f"{side}_gripper_link_0").id
        tips = [m.body(f"{side}_gripper_link_{i}").id for i in (2, 4)]
        centre = np.mean([d.geom_xpos[g] for g in range(m.ngeom) if m.geom_bodyid[g] in tips and m.geom_contype[g] == 0], axis=0)
        local = d.xmat[base].reshape(3, 3).T @ (centre - d.xpos[base])
        spec.body(f"{side}_gripper_link_0").add_site(name=f"{side}_pinch", pos=local, size=[0.006, 0, 0], group=3)
    spec.compile()
    OUT.write_text(spec.to_xml())
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
