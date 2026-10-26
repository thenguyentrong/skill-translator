"""Hand-only grasp rig: G1 right hand on an x-y-z gantry, 3 cm cube on a table. Grasp = descend, close, lift, carry."""
import math
import mujoco
import numpy as np

G1 = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets/robots/mujoco_menagerie/unitree_g1/g1_with_hands.xml")
DEX3 = ("thumb_0", "thumb_1", "thumb_2", "index_0", "index_1", "middle_0", "middle_1")
HALF = 0.015
# wrist frame -> world for a top grasp: hand x along world x, palm normal (+y) down, z = x cross y
R_TOP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def _quat(rot):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, rot.flatten())
    return q


def build(force_limit=None):
    src = mujoco.MjModel.from_xml_path(G1)
    g1 = mujoco.MjSpec.from_file(G1)
    spec = mujoco.MjSpec()
    spec.option.timestep = 0.002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.impratio = 10
    w = spec.worldbody
    w.add_light(pos=[0, -0.5, 1.0], dir=[0, 0.5, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    w.add_geom(name="table", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.3, 0.3, 0.02], pos=[0, 0, -0.02])
    cube = w.add_body(name="cube", pos=[0, 0, HALF])
    cube.add_freejoint(name="cube")
    cube.add_geom(name="cube", type=mujoco.mjtGeom.mjGEOM_BOX, size=[HALF] * 3, mass=0.03 * (HALF / 0.015) ** 3 * 0.5,
                  friction=[1.0, 0.005, 0.0001], condim=4)
    gantry = w.add_body(name="gantry", mass=0.2, inertia=[1e-4, 1e-4, 1e-4])
    for ax, v in zip("xyz", np.eye(3)):
        gantry.add_joint(name=f"g{ax}", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=v, damping=50)
        act = spec.add_actuator(name=f"g{ax}", target=f"g{ax}", trntype=mujoco.mjtTrn.mjTRN_JOINT)
        act.gainprm[0] = 5000
        act.biasprm[:3] = [0, -5000, -200]
        act.biastype = mujoco.mjtBias.mjBIAS_AFFINE
    palm = gantry.add_body(name="palm", quat=_quat(R_TOP))
    palm.add_frame().attach_body(g1.body("right_wrist_yaw_link"), "h/", "")
    m = spec.compile()
    if force_limit:
        for j in DEX3:
            a = m.actuator(f"h/right_hand_{j}_joint").id
            m.actuator_forcelimited[a] = 1
            m.actuator_forcerange[a] = [-force_limit, force_limit]
    return m


def set_palm(m, d, p, grip, qpos=False):
    """Drive the gantry so that the grip point (wrist frame) is at world point p."""
    wb = m.body("h/right_wrist_yaw_link").id
    r_local = np.zeros(9)
    mujoco.mju_quat2Mat(r_local, m.body_quat[wb])
    target = p - R_TOP @ (m.body_pos[wb] + r_local.reshape(3, 3) @ grip)
    for i, ax in enumerate("xyz"):
        d.ctrl[m.actuator(f"g{ax}").id] = target[i]
        if qpos:
            d.qpos[m.jnt_qposadr[m.joint(f"g{ax}").id]] = target[i]


def trial(m, open_pose, close_pose, grip, dx=0.0, dz=0.0, dyaw=0.0, close_time=0.4, record=None, log=None, yaw0=0.0):
    """grip = grip point in the wrist frame. dx, dz, dyaw = vision error (cube is off by this much). Returns cube height after lift+carry."""
    d = mujoco.MjData(m)
    cq = m.jnt_qposadr[m.joint("cube").id]
    yaw = yaw0 + dyaw
    d.qpos[cq:cq + 7] = [0, 0, HALF, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
    hand_q = [m.jnt_qposadr[m.joint(f"h/right_hand_{j}_joint").id] for j in DEX3]
    hand_a = [m.actuator(f"h/right_hand_{j}_joint").id for j in DEX3]
    d.qpos[hand_q] = open_pose
    d.ctrl[hand_a] = open_pose
    target = np.array([dx, dz, HALF])      # where the robot thinks the cube centre is (vision error)
    above = target + [0, 0, 0.08]
    def palm_at(p):
        set_palm(m, d, p, grip)
    def run(seconds, fn=None):
        n = int(seconds / m.opt.timestep)
        for i in range(n):
            if fn: fn((i + 1) / n)
            mujoco.mj_step(m, d)
            if record is not None and i % 20 == 0: record.append(d.qpos.copy())
            if log is not None and i % 50 == 0: log(d)
    s = lambda t: 10 * t**3 - 15 * t**4 + 6 * t**5
    palm_at(above); set_palm(m, d, above, grip, qpos=True); mujoco.mj_forward(m, d)
    run(0.3)
    run(0.6, lambda t: palm_at(above + s(t) * (target - above)))
    o, c = np.array(open_pose), np.array(close_pose)
    run(close_time, lambda t: d.ctrl.__setitem__(hand_a, o + t * (c - o)))
    run(0.3)
    lift = target + [0, 0, 0.10]
    run(0.6, lambda t: palm_at(target + s(t) * (lift - target)))
    trial.lifted = float(d.qpos[cq + 2])
    carry = lift + [0.0, 0.2, 0.0]
    run(0.8, lambda t: palm_at(lift + s(t) * (carry - lift)))
    run(0.4)
    return float(d.qpos[cq + 2])


def score(m, open_pose, close_pose, grip, errors=((0, 0, 0), (0.004, 0, 0), (-0.004, 0, 0), (0, 0.004, 0), (0, -0.004, 0), (0, 0, 0.14), (0, 0, -0.14)), yaw0=0.0, close_time=0.4):
    heights = [trial(m, open_pose, close_pose, grip, *e, yaw0=yaw0, close_time=close_time) for e in errors]
    return sum(h > 0.06 for h in heights), heights
