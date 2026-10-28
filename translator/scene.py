"""Tabletop scene: table, the card's object and container, and one robot."""
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from .robots import Robot, get

TABLE_TOP = 0.75
CUBE_HALF = 0.015
BOWL_RADIUS = 0.06
BOWL_WALL = 0.04
TABLE_CENTRE = (0.35, 0.0)
TABLE_HALF = (0.55, 0.6)
PREFIX = "robot/"
CAMERAS = ("front", "top", PREFIX + "wrist")

_MOVABLE = (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))
DEFAULT_CARD = Path(__file__).resolve().parents[1] / "cards" / "cube_to_bowl.json"
DENSITY = 900.0


def subtree(m, root):
    def inside(b):
        while b > 0:
            if b == root:
                return True
            b = m.body_parentid[b]
        return False
    return {b for b in range(m.nbody) if inside(b)}


NEEDS = {"hands": 1, "move_m": 0.0, "mass_kg": None, "keep_upright": False, "fragile": False}


def task_objects(card):
    """What the scene needs from a skill card: the held object and the container, by name, shape and size.
    An "open" card has a cabinet with a hinged door and a bar handle instead (the handle takes the held object's place)."""
    needs = {**NEEDS, **card.get("needs", {})}
    if card.get("kind") == "open":
        return {**_cabinet_objects(card), "needs": needs}
    if card.get("kind") == "carry":
        from .carry import objects
        return {**objects(card), "needs": needs}
    held = card["grip"]["object"]
    container = card["success"]["container"]
    h, c = card["objects"][held], card["objects"][container]
    return {"held": held, "held_shape": h["shape"], "held_size": np.array(h["size"], dtype=float),
            "container": container, "container_shape": c.get("shape", "bowl"),
            "bowl_radius": float(c["inner_radius"]), "bowl_wall": float(c["wall_height"]), "needs": needs}


def _cabinet_objects(card):
    handle = card["grip"]["object"]
    cab = card["success"]["object"]
    c, h = card["objects"][cab], card["objects"][handle]
    door = c["door"]
    return {"kind": "open", "held": handle, "held_shape": "bar", "container": cab, "container_shape": "cabinet",
            "held_size": np.array([h["diameter"], h["diameter"], h["length"]], dtype=float),
            "bowl_radius": 0.0, "bowl_wall": float(c["size"][2]),
            "cabinet": np.array(c["size"], dtype=float), "door": np.array([door["width"], door["height"], door["thickness"]]),
            "hinge": -1.0 if door["hinge"] == "left" else 1.0, "bar": h,
            "goal": math.radians(card["success"]["min_angle_deg"])}


def cabinet_frame(objs, xy, yaw):
    """A cabinet at `xy` whose front faces along `yaw`: hinge point, front normal n, and t (to the right of a robot
    facing the door; the hinge sits at hinge * t)."""
    w, d, _ = objs["cabinet"]
    n = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    t = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    hinge = np.array([xy[0], xy[1], TABLE_TOP]) + n * d / 2 + t * objs["hinge"] * w / 2
    return hinge, n, t


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def handle_path(objs, xy, yaw, angles):
    """Handle centre and the door's free edge (world) for each door angle."""
    hinge, n, t = cabinet_frame(objs, xy, yaw)
    wd, _, th = objs["door"]
    bar = objs["bar"]
    handle = n * (th + bar["standoff"]) - t * objs["hinge"] * (wd - bar["from_free_edge"]) + [0, 0, bar["height"]]
    edge = n * th - t * objs["hinge"] * wd
    return ([hinge + rot_z(objs["hinge"] * a) @ handle for a in angles],
            [hinge + rot_z(objs["hinge"] * a) @ edge for a in angles])


def _add_cabinet(spec, objs):
    """A fixed cabinet with a door on a hinge (damped, with some friction) and a vertical bar handle in front of it.
    Cabinet and door in the container colour (green), the handle in the marker colour (red)."""
    w, d, h = objs["cabinet"]
    wd, hd, th = objs["door"]
    s, bar = objs["hinge"], objs["bar"]
    green, grey = [0.25, 0.62, 0.35, 1], [0.75, 0.75, 0.75, 1]
    top = 100.0 if spec.compiler.degree else math.radians(100)
    cab = spec.worldbody.add_body(name="cabinet", pos=[0.4, 0.0, TABLE_TOP])
    cab.add_geom(name="cabinet", type=mujoco.mjtGeom.mjGEOM_BOX, size=[d / 2, w / 2, h / 2], pos=[0, 0, h / 2], rgba=green)
    door = cab.add_body(name="door", pos=[d / 2, s * w / 2, 0])
    door.add_joint(name="door", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, s], range=[0, top], limited=mujoco.mjtLimited.mjLIMITED_TRUE,
                   damping=0.05, frictionloss=0.02, armature=0.002)
    door.add_geom(name="door", type=mujoco.mjtGeom.mjGEOM_BOX, size=[th / 2, wd / 2, hd / 2], pos=[th / 2, -s * wd / 2, 0.005 + hd / 2],
                  mass=0.2, rgba=green)
    x, y, z = th + bar["standoff"], -s * (wd - bar["from_free_edge"]), bar["height"]
    door.add_geom(name="handle", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[bar["diameter"] / 2, bar["length"] / 2, 0], pos=[x, y, z],
                  mass=0.02, friction=[1.0, 0.005, 0.002], condim=6, rgba=[0.85, 0.2, 0.15, 1])
    for sz in (-1, 1):
        door.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[bar["standoff"] / 2, 0.004, 0.004], mass=0.005, rgba=grey,
                      pos=[th + bar["standoff"] / 2, y, z + sz * (bar["length"] / 2 - 0.009)])
    spec.add_exclude(bodyname1="cabinet", bodyname2="door")


def _key_home(xml, key):
    m = mujoco.MjModel.from_xml_path(str(xml))
    k = m.key(key).id
    return {
        m.joint(j).name: float(m.key_qpos[k, m.jnt_qposadr[j]])
        for j in range(m.njnt)
        if m.jnt_type[j] in _MOVABLE
    }


def _axis_vec(spec: str):
    v = np.zeros(3)
    v["xyz".index(spec[1])] = 1.0 if spec[0] == "+" else -1.0
    return v


def _look_at(pos, target, right=None):
    """Rotation of a MuJoCo camera at `pos` looking at `target` (camera looks along -z, y is up)."""
    z = pos - target
    z /= np.linalg.norm(z)
    if right is None:
        right = np.cross(-z, [0.0, 0.0, 1.0])
    x = right - np.dot(right, z) * z
    x /= np.linalg.norm(x)
    return np.column_stack([x, np.cross(z, x), z])


def _quat(rot):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, rot.flatten())
    return q


def _add_wrist_camera(spec, robot: Robot):
    """Camera on the gripper: 10 cm behind the grip point, 5 cm to the side, looking at where the fingers close."""
    site = spec.site(robot.ee_site)
    r_site = np.zeros(9)
    mujoco.mju_quat2Mat(r_site, np.array(site.quat, dtype=float))
    r_site = r_site.reshape(3, 3)
    a, c = _axis_vec(robot.approach_axis), _axis_vec(robot.closing_axis)
    pos = -0.10 * a + 0.05 * np.cross(a, c)
    rot = _look_at(pos, 0.02 * a, right=c)
    site.parent.add_camera(name="wrist", pos=np.array(site.pos) + r_site @ pos, quat=_quat(r_site @ rot), fovy=75)


def _add_world_cameras(world, origin, reach):
    centre = np.array([origin[0] + 0.5 * reach, origin[1], TABLE_TOP])
    el = math.radians(45)
    front = centre + (1.1 * reach + 0.3) * np.array([math.cos(el), 0.0, math.sin(el)])
    world.add_camera(name="front", pos=front, quat=_quat(_look_at(front, centre)), fovy=60)
    top = centre + [0.0, 0.0, 1.1 * reach + 0.1]
    world.add_camera(name="top", pos=top, quat=_quat(_look_at(top, centre, right=np.array([0.0, -1.0, 0.0]))), fovy=60)


def _position_servos(spec, xml, keep=()):
    """Torque motors on joints become position servos (the translator commands joint angles, like a robot's own
    joint controller): stiffness from the motor's torque limit, joint range as command range. A joint that already
    has a position actuator keeps only that one. Gripper actuators (`keep`) stay as they are."""
    m0 = mujoco.MjModel.from_xml_path(str(xml))
    acts = list(spec.actuators)
    servoed = {a.target for a in acts if a.trntype == mujoco.mjtTrn.mjTRN_JOINT and a.biastype != mujoco.mjtBias.mjBIAS_NONE}
    for i, a in enumerate(acts):
        if a.trntype != mujoco.mjtTrn.mjTRN_JOINT or a.biastype != mujoco.mjtBias.mjBIAS_NONE or a.name in keep:
            continue
        if a.target in servoed:
            spec.delete(a)
            continue
        j = m0.joint(a.target).id
        tau = float(np.abs(m0.actuator_ctrlrange[i]).max()) if m0.actuator_ctrllimited[i] else 50.0
        tau *= abs(float(m0.actuator_gear[i, 0])) or 1.0
        kp = float(np.clip(5.0 * tau, 20.0, 500.0))
        a.gear[0] = 1.0
        a.gaintype, a.gainprm[0] = mujoco.mjtGain.mjGAIN_FIXED, kp
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE
        a.biasprm[0], a.biasprm[1], a.biasprm[2] = 0.0, -kp, -kp / 10.0
        a.forcelimited, a.forcerange = mujoco.mjtLimited.mjLIMITED_TRUE, [-tau, tau]
        if m0.jnt_limited[j]:
            a.ctrllimited, a.ctrlrange = mujoco.mjtLimited.mjLIMITED_TRUE, m0.jnt_range[j].tolist()
        else:
            a.ctrllimited = mujoco.mjtLimited.mjLIMITED_FALSE


def _robot_spec(robot: Robot, keep_free=False):
    home = _key_home(robot.xml, robot.home) if isinstance(robot.home, str) else dict(robot.home or {})
    home.update(robot.ready or {})
    spec = mujoco.MjSpec.from_file(str(robot.xml))
    for key in list(spec.keys):
        spec.delete(key)
    grippers = robot.gripper if isinstance(robot.gripper, tuple) else (robot.gripper,) if robot.gripper else ()
    _position_servos(spec, robot.xml, keep=grippers)
    if robot.ee_add:
        body, pos, *quat = robot.ee_add
        spec.body(body).add_site(name=robot.ee_site, pos=pos, quat=quat[0] if quat else [1, 0, 0, 0], group=3)
    if robot.left and robot.left.get("ee_add"):
        body, pos, *quat = robot.left["ee_add"]
        spec.body(body).add_site(name=robot.left["ee_site"], pos=pos, quat=quat[0] if quat else [1, 0, 0, 0], group=3)
    if robot.tool:
        where, xml, *pose = robot.tool
        tool = mujoco.MjSpec.from_file(str(xml))
        spec.option.cone, spec.option.impratio = tool.option.cone, tool.option.impratio
        if spec.site(where) is not None:
            spec.site(where).attach_body(tool.worldbody.first_body(), "tool/", "")
        else:
            pos = list(pose[0]) if len(pose) > 0 else [0, 0, 0]
            quat = list(pose[1]) if len(pose) > 1 else [1, 0, 0, 0]
            body = spec.body(where)
            if robot.tool_replaces_hand:  # the model's own hand is in this link's mesh: take it off, a flange holds the tool
                for g in list(body.geoms):
                    spec.delete(g)
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, size=[0.028, 0, 0], fromto=[0, 0, 0, *pos],
                              rgba=[0.75, 0.75, 0.75, 1])
            body.add_frame(pos=pos, quat=quat).attach_body(tool.worldbody.first_body(), "tool/", "")
    if robot.fixed_base and not keep_free:
        for j in list(spec.worldbody.first_body().joints):
            if j.type == mujoco.mjtJoint.mjJNT_FREE:
                spec.delete(j)
    if robot.ee_site:
        _add_wrist_camera(spec, robot)
    return spec, home


def _add_bowl(world, radius, wall, shape="bowl"):
    """A round bowl, cup or plate; shape "box" makes a square bin with `radius` = half its inner width."""
    bowl = world.add_body(name="bowl", pos=[0.4, -0.2, TABLE_TOP])
    color = [0.25, 0.62, 0.35, 1]
    if shape == "box":
        bowl.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[radius + 0.006, radius + 0.006, 0.003], pos=[0, 0, 0.003], rgba=color)
        for i in range(4):
            a = i * math.pi / 2
            bowl.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.003, radius + 0.006, wall / 2],
                          pos=[(radius + 0.003) * math.cos(a), (radius + 0.003) * math.sin(a), wall / 2],
                          quat=[math.cos(a / 2), 0, 0, math.sin(a / 2)], rgba=color)
        return
    bowl.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[radius + 0.005, 0.003, 0], pos=[0, 0, 0.003], rgba=color)
    n = max(20, int(radius / 0.003))
    half_len = (radius + 0.005) * math.tan(math.pi / n)
    for i in range(n):
        a = 2 * math.pi * i / n
        bowl.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=[0.003, half_len, wall / 2],
            pos=[(radius + 0.003) * math.cos(a), (radius + 0.003) * math.sin(a), wall / 2],
            quat=[math.cos(a / 2), 0, 0, math.sin(a / 2)],
            rgba=color,
        )


def _add_held(world, objs):
    """The held object, in the scene's marker colour (red) so the cameras can find it. Contacts have torsional and
    rolling friction (condim 6): soft finger pads, and a lemon or ball that does not roll forever."""
    shape, size = objs["held_shape"], objs["held_size"]
    body = world.add_body(name="cube", pos=[0.4, 0.2, TABLE_TOP + size[2] / 2])
    body.add_freejoint(name="cube")
    if shape == "sphere":
        kind, gsize, volume = mujoco.mjtGeom.mjGEOM_SPHERE, [size[0] / 2, 0, 0], math.pi / 6 * size[0] ** 3
    elif shape == "cylinder":
        kind, gsize, volume = mujoco.mjtGeom.mjGEOM_CYLINDER, [size[0] / 2, size[2] / 2, 0], math.pi / 4 * size[0] ** 2 * size[2]
    else:
        kind, gsize, volume = mujoco.mjtGeom.mjGEOM_BOX, list(size / 2), float(np.prod(size))
    mass = objs["needs"]["mass_kg"] or max(0.02, DENSITY * volume)
    body.add_geom(name="cube", type=kind, size=gsize, mass=mass,
                  friction=[1.0, 0.005, 0.002], condim=6, rgba=[0.85, 0.2, 0.15, 1])


PRACTICE = Path(__file__).resolve().parents[1] / "outputs" / "practice"


def practice_file(robot_name, card):
    return PRACTICE / f"{robot_name}__{card['name']}.json"


def build(name, card=None, grip_depth=None):
    """`name` = a robot from the library, an adapter file, or a Robot. `grip_depth` (m) moves the grip point past
    the object's centre along the approach; by default it comes from this robot's practice with this card, else 0."""
    robot = name if isinstance(name, Robot) else get(name)
    name = robot.name
    card = card or json.loads(DEFAULT_CARD.read_text())
    objs = task_objects(card)
    carry = objs.get("kind") == "carry"
    if grip_depth is None:
        f = practice_file(name, card)
        grip_depth = json.loads(f.read_text())["grip_depth"] if f.exists() else 0.01 if carry else 0.0
    spec = mujoco.MjSpec()
    spec.modelname = f"scene_{name}"
    spec.option.timestep = 0.002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.impratio = 10
    if carry:
        spec.option.noslip_iterations = 5  # MuJoCo's soft contacts let a crate held for 20 s creep out of the hands
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    spec.visual.headlight.diffuse = [0.5, 0.5, 0.5]
    spec.visual.headlight.ambient = [0.3, 0.3, 0.3]

    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[0.82, 0.85, 0.89], rgb2=[0.45, 0.5, 0.58], width=512, height=3072)
    world = spec.worldbody
    world.add_light(pos=[0.3, -0.5, 2.5], dir=[0, 0.2, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=True)
    floor = world.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[4, 4, 0.05], rgba=[0.35, 0.37, 0.4, 1])
    table = world.add_body(name="table", pos=[TABLE_CENTRE[0], TABLE_CENTRE[1], TABLE_TOP])
    table.add_geom(name="table_top", type=mujoco.mjtGeom.mjGEOM_BOX, size=[TABLE_HALF[0], TABLE_HALF[1], 0.02], pos=[0, 0, -0.02],
                   rgba=[0.62, 0.5, 0.38, 1])
    for sx in (-1, 1):
        for sy in (-1, 1):
            table.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.025, 0.025, (TABLE_TOP - 0.04) / 2],
                           pos=[sx * (TABLE_HALF[0] - 0.05), sy * (TABLE_HALF[1] - 0.05), -0.04 - (TABLE_TOP - 0.04) / 2],
                           rgba=[0.45, 0.36, 0.27, 1])

    if objs.get("kind") == "open":
        _add_cabinet(spec, objs)
    elif carry:
        from .carry import add
        add(spec, objs)
        floor.contype = floor.conaffinity = 2
    else:
        _add_held(world, objs)
        _add_bowl(world, objs["bowl_radius"], objs["bowl_wall"], objs["container_shape"])

    slides = carry and robot.mobile
    rspec, home = _robot_spec(robot, keep_free=slides)
    yaw = robot.base_yaw
    base = np.array([robot.base_pos[0], robot.base_pos[1], TABLE_TOP + robot.base_pos[2]])
    frame = world.add_frame(pos=base, quat=[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)])
    root = rspec.worldbody.first_body()
    root_name, root_pos = PREFIX + root.name, np.array(root.pos, dtype=float)
    frame.attach_body(root, PREFIX, "")
    if slides:
        from . import mobile
        target = mobile.add_base(spec, base + rot_z(yaw) @ root_pos, yaw, root_name)

    model = spec.compile()
    probe = Scene(robot, model, mujoco.MjData(model), home, base, objs=objs)
    _add_world_cameras(world, probe.origin, probe.reach)
    if slides:  # lift the base by the weld's sag so the feet end at floor level (robot-floor contacts are off)
        from .carry import floor_off
        floor_off(model)
        probe.reset()
        lift = mobile.sag(model, probe.data, int(model.jnt_qposadr[model.body_jntadr[model.body(root_name).id]]))
        frame.pos = [base[0], base[1], base[2] + lift]
        target.pos = [target.pos[0], target.pos[1], target.pos[2] + lift]
    model = spec.compile()
    if slides:
        floor_off(model)
    scene = Scene(robot, model, mujoco.MjData(model), home, base, probe.reach, probe.footprint, objs=objs)
    scene.root = root_name
    scene.grip_depth = float(grip_depth)
    scene.problems = probe.problems
    for g in range(model.ngeom):  # see-through collision shapes some models draw over their meshes: physics only
        if model.geom_rgba[g, 3] < 1 and model.geom_group[g] == 0 and model.body(model.geom_bodyid[g]).name.startswith(PREFIX):
            model.geom_rgba[g, 3] = 0
    for g in scene.gripper_ids:
        model.actuator_gainprm[g, 0] *= robot.grip_force_gain
        model.actuator_biasprm[g, 1:3] *= robot.grip_force_gain
    scene.reset()
    scene.fit_gripper(card["grip"].get("width") or float(objs["held_size"][0]))
    scene.tip_reach = scene.measure_tip_reach()
    scene.reset()
    scene.payload = scene.measure_payload()
    scene.needs_fail = check_needs(scene)
    scene.reset()
    return scene


def check_needs(scene):
    """What the card says the task needs, against what this robot has: hands, moving between places, weight."""
    n, r, o = scene.objs["needs"], scene.robot, scene.objs
    if scene.kind == "carry":
        if o["handles"] == "none":
            return "two_hand_grip", (f"the {o['held']} has no handles; holding a box with two hands from its sides is not "
                                     "built yet (carrying works by side handles or a top handle)")
        if o["handles"] == "side" and r.hands < 2:
            return "two_hands", f"the {o['held']} has a handle on each side and needs 2 hands, the {r.name} has {r.hands}"
    elif n["hands"] > r.hands:
        return "two_hands", f"the task needs {n['hands']} hands, the {r.name} has {r.hands} it can use"
    elif n["hands"] > 1:
        return "two_hand_grip", (f"the task needs {n['hands']} hands; the {r.name} has them, but it holds things with two "
                                 "hands only by their handles so far (carry skills)")
    span = 2 * 0.85 * scene.reach
    if n["move_m"] > span and not r.mobile:
        return "must_walk", (f"the two places are {n['move_m']:.1f} m apart, the {r.name} reaches {span:.2f} m from one "
                             "side to the other and cannot move")
    limit, source = (r.payload_kg, "rated by its maker") if r.payload_kg else (scene.payload, "torque limits in its model")
    if scene.kind != "open" and limit is not None:
        kg = float(scene.model.body_mass[scene.model.body("cube").id])
        if scene.kind == "carry" and o["handles"] == "side":
            limit *= 2
        if kg > limit:
            return "too_heavy", f"the {o['held']} weighs {kg:.1f} kg, the {r.name} lifts {limit:.1f} kg ({source})"
    return None


def _sample_cabinet(scene, rng, draws=3000):
    """Cabinet facing the robot (+-20 degrees), anywhere its handle stays inside 25-85 % of the reach all the way
    from closed to the goal angle (+15), the cabinet on the table, and the door clear of the robot's base."""
    o = scene.objs
    near, far = max(0.25 * scene.reach, scene.footprint + 0.05), 0.85 * scene.reach
    angles = np.linspace(0.0, min(o["goal"] + math.radians(15), math.radians(100)), 9)
    w, d, _ = o["cabinet"]
    half = math.hypot(w, d) / 2
    for _ in range(draws):
        r = rng.uniform(near + 0.1, far + d)
        a = rng.uniform(-math.radians(35), math.radians(35))
        xy = scene.origin[:2] + r * np.array([math.cos(a), math.sin(a)])
        yaw = a + math.pi + rng.uniform(-math.radians(20), math.radians(20))
        if not scene.on_table(xy, half + 0.01) or not scene.clear_of_robot(xy, half + 0.02):
            continue
        if np.linalg.norm(xy - scene.origin[:2]) - half < scene.footprint + 0.02:
            continue
        handles, edges = handle_path(o, xy, yaw, angles)
        hd = [np.linalg.norm(p[:2] - scene.origin[:2]) for p in handles]
        ed = [np.linalg.norm(p[:2] - scene.origin[:2]) for p in edges]
        if min(hd) >= near and max(hd) <= far and min(ed) >= scene.footprint + 0.03:
            return xy, None, yaw
    raise ValueError("; ".join(scene.problems) or f"no room: the handle's path while the door opens to "
                     f"{math.degrees(angles[-1]):.0f} degrees does not fit between {near:.2f} and {far:.2f} m from the arm")


def sample_layout(scene, rng, min_gap=0.12):
    """Cube and bowl at 35-75 % of the reach, at most 45 degrees to each side of the robot's front,
    outside the robot's own base footprint, and on the table. For an open card: where the cabinet stands."""
    if scene.kind == "open":
        return _sample_cabinet(scene, rng)
    if scene.kind == "carry":
        from .carry import sample
        return sample(scene, rng)
    def point(clearance):
        near, far = max(0.35 * scene.reach, scene.footprint + clearance), 0.75 * scene.reach
        if near >= far:
            raise ValueError("; ".join(scene.problems) or f"no room on the table: the robot's own base covers "
                             f"{scene.footprint:.2f} m around the arm, but its reach at table height is only {scene.reach:.2f} m")
        for _ in range(1000):
            r = rng.uniform(near, far)
            a = rng.uniform(-math.pi / 4, math.pi / 4)
            xy = scene.origin[:2] + r * np.array([math.cos(a), math.sin(a)])
            if scene.on_table(xy, clearance) and scene.clear_of_robot(xy, clearance):
                return xy
        raise RuntimeError("no free spot on the table inside the robot's reach")

    for _ in range(100):
        cube = point(scene.held_xy + 0.02)
        for _ in range(200):
            bowl = point(scene.container_xy + 0.006 + 0.02)
            if np.linalg.norm(bowl - cube) >= max(min_gap, scene.container_xy + scene.held_xy + 0.025):
                return cube, bowl, rng.uniform(0, math.pi / 2)
    raise RuntimeError("the object and the container do not both fit inside the robot's reach")


class Scene:
    def __init__(self, robot: Robot, model, data, home, base, reach=None, footprint=None, objs=None):
        self.robot, self.model, self.data, self.base = robot, model, data, base
        self.grip_depth = 0.0
        self.tip_reach = 0.0
        self.problems = []
        self.too_small = None
        self.too_thin = None
        self.payload = None
        self.needs_fail = None
        self.root = None
        self.carry_offsets = {}
        self.objs = objs or task_objects(json.loads(DEFAULT_CARD.read_text()))
        self.kind = self.objs.get("kind", "pick_place")
        size = self.objs["held_size"]
        self.held_half = float(size[2] / 2)
        self.held_xy = float(size[0] / 2) if self.objs["held_shape"] not in ("box", "crate") else float(np.hypot(size[0], size[1]) / 2)
        self.bowl_radius, self.bowl_wall = self.objs["bowl_radius"], self.objs["bowl_wall"]
        self.square_bin = self.objs.get("container_shape") == "box"
        self.container_xy = self.bowl_radius * (math.sqrt(2) if self.square_bin else 1.0)
        self.open_ctrl = np.atleast_1d(robot.gripper_open).astype(float)
        self.close_ctrl = np.atleast_1d(robot.gripper_closed).astype(float)
        self.joints = [j for j in range(model.njnt)
                       if model.joint(j).name.startswith(PREFIX) and model.jnt_type[j] in _MOVABLE]
        self.home = {PREFIX + k: v for k, v in home.items()}
        for j in self.joints:
            name = model.joint(j).name
            if model.jnt_limited[j] and name in self.home:
                self.home[name] = float(np.clip(self.home[name], *model.jnt_range[j]))
        grippers = robot.gripper if isinstance(robot.gripper, tuple) else (robot.gripper,) if robot.gripper else ()
        self.gripper_ids = [model.actuator(PREFIX + g).id for g in grippers]
        self.arm_actuators = [
            a for a in range(model.nu)
            if a not in self.gripper_ids and (not robot.active or model.actuator(a).name[len(PREFIX):].startswith(robot.active))
        ]
        if robot.active and not self.arm_actuators:
            names = [model.actuator(a).name[len(PREFIX):] for a in range(model.nu)]
            raise ValueError(f"no actuator name starts with any of {list(robot.active)}; the actuators are {names}")
        self.arm_joints = [model.actuator_trnid[a, 0] for a in self.arm_actuators
                           if model.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
        self.ee_site_id = model.site(PREFIX + robot.ee_site).id if robot.ee_site else None
        if self.kind == "open":
            self.cube_qadr = None
            self.door_qadr = model.jnt_qposadr[model.joint("door").id]
            self.handle_id = model.geom("handle").id
            self.bowl_id = model.body("cabinet").id
        else:
            self.cube_qadr = model.jnt_qposadr[model.joint("cube").id]
            self.bowl_id = model.body("bowl").id
        self.origin = self._arm_origin()
        self.reach = self._measure_reach() if reach is None else reach
        self.obstacles = []
        self.footprint = self._measure_footprint() if footprint is None else footprint
        if footprint is not None:
            self.obstacles = self._robot_boxes()[1]

    def _home_data(self):
        m, d = self.model, mujoco.MjData(self.model)
        for j in self.joints:
            d.qpos[m.jnt_qposadr[j]] = self.home.get(m.joint(j).name, 0.0)
        mujoco.mj_kinematics(m, d)
        return d

    def _arm_origin(self):
        """Where the arm starts: the first active joint's axis (the base for an arm, the shoulder for a humanoid)."""
        if not self.arm_joints:
            return self.base.copy()
        return self._home_data().xanchor[self.arm_joints[0]].copy()

    def _measure_reach(self, samples=20000, seed=0):
        """90th percentile of the end effector's horizontal distance from the arm origin, 0-6 cm above the table."""
        if self.ee_site_id is None:
            return 0.5
        m, d = self.model, self._home_data()
        rng = np.random.default_rng(seed)
        dist = []
        for _ in range(samples):
            for j in self.arm_joints:
                lo, hi = m.jnt_range[j] if m.jnt_limited[j] else (-math.pi, math.pi)
                d.qpos[m.jnt_qposadr[j]] = rng.uniform(lo, hi)
            mujoco.mj_kinematics(m, d)
            p = d.site_xpos[self.ee_site_id]
            if 0.0 < p[2] - TABLE_TOP < 0.06:
                dist.append(np.hypot(*(p[:2] - self.origin[:2])))
        if len(dist) < 20:
            self.problems.append(f"the grip point came within 6 cm of the table top in only {len(dist)} of {samples} "
                                 "random arm poses: from this base placement the arm cannot reach the table")
            return 0.0
        return float(np.percentile(dist, 90))

    def _robot_boxes(self, below=0.08):
        """Robot collision boxes (xy bounds) that sit on the table, up to `below` above it, at home.
        Splits them into parts that turn with the arm's first joints and parts that stay put; the rest of the arm
        (from its third joint on) moves out of the way and is left out."""
        m, d = self.model, self._home_data()
        first = m.jnt_bodyid[self.arm_joints[0]] if self.arm_joints else -1
        moving = subtree(m, m.jnt_bodyid[self.arm_joints[2]]) if len(self.arm_joints) > 2 else set()
        turning, fixed = [], []
        for g in range(m.ngeom):
            b = m.geom_bodyid[g]
            if not m.geom_contype[g] or not m.body(b).name.startswith(PREFIX) or b in moving:
                continue
            rot = d.geom_xmat[g].reshape(3, 3)
            centre = d.geom_xpos[g] + rot @ m.geom_aabb[g, :3]
            extent = np.abs(rot) @ m.geom_aabb[g, 3:]
            on_table = all(abs(centre[i] - TABLE_CENTRE[i]) < TABLE_HALF[i] + extent[i] for i in range(2))
            if not (on_table and centre[2] + extent[2] > TABLE_TOP and centre[2] - extent[2] < TABLE_TOP + below):
                continue
            while b > 0 and b != first:
                b = m.body_parentid[b]
            (turning if b == first else fixed).append((centre[:2] - extent[:2], centre[:2] + extent[:2]))
        return turning, fixed

    def _measure_footprint(self):
        """Radius swept around the arm origin by low parts that turn with the first arm joint."""
        turning, self.obstacles = self._robot_boxes()
        return max((np.hypot(*(np.maximum(abs(lo - self.origin[:2]), abs(hi - self.origin[:2])))) for lo, hi in turning),
                   default=0.0)

    def clear_of_robot(self, xy, clearance):
        """True when a circle of radius `clearance` at `xy` stays off the robot's fixed parts."""
        return all(np.any(xy < lo - clearance) or np.any(xy > hi + clearance) for lo, hi in self.obstacles)

    def default_layout(self):
        """Cube on the left, bowl on the right, both well inside the reach. Open card: the cabinet straight ahead.
        Carry card: the crate in front, its mark `move` metres to the side."""
        if self.kind == "carry":
            x = self.base[0] + 0.38 if self.robot.mobile else self.origin[0] + 0.55 * self.reach
            return (x, self.base[1]), (x, self.base[1] + self.objs["move"])
        if self.kind == "open":
            return (self.origin[0] + 0.55 * self.reach + self.objs["cabinet"][1], self.origin[1]), None
        x = self.origin[0] + 0.55 * self.reach
        dy = 0.3 * self.reach
        return (x, self.origin[1] + dy), (x, self.origin[1] - dy)

    def reset(self, cube_xy=None, bowl_xy=None, cube_yaw=0.0):
        m, d = self.model, self.data
        cube_default, bowl_default = self.default_layout()
        if self.kind == "open" and cube_xy is None:
            cube_yaw = math.pi
        cube_xy = cube_default if cube_xy is None else cube_xy
        bowl_xy = bowl_default if bowl_xy is None else bowl_xy
        mujoco.mj_resetData(m, d)
        for j in self.joints:
            d.qpos[m.jnt_qposadr[j]] = self.home.get(m.joint(j).name, 0.0)
        if self.kind == "open":
            m.body_pos[self.bowl_id] = [cube_xy[0], cube_xy[1], TABLE_TOP]
            m.body_quat[self.bowl_id] = [math.cos(cube_yaw / 2), 0, 0, math.sin(cube_yaw / 2)]
            self.cabinet_yaw = cube_yaw
        else:
            z = TABLE_TOP + (0.001 if self.kind == "carry" else self.held_half)
            d.qpos[self.cube_qadr:self.cube_qadr + 7] = [cube_xy[0], cube_xy[1], z, math.cos(cube_yaw / 2), 0, 0, math.sin(cube_yaw / 2)]
            m.body_pos[self.bowl_id] = [bowl_xy[0], bowl_xy[1], TABLE_TOP + (0.0005 if self.kind == "carry" else 0.0)]
        mujoco.mj_forward(m, d)
        for a in range(m.nu):
            if a not in self.gripper_ids and m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT):
                d.ctrl[a] = d.qpos[m.jnt_qposadr[m.actuator_trnid[a, 0]]]
        self.set_gripper(open_=True)

    def _gripper_sides(self):
        """Collision geoms on the two sides of a one-motor gripper (two fingers, or a moving jaw and its fixed jaw)."""
        m = self.model
        if len(self.gripper_ids) != 1:
            return None
        a = self.gripper_ids[0]
        if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT):
            joints = [m.actuator_trnid[a, 0]]
        elif m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_TENDON):
            t = m.actuator_trnid[a, 0]
            joints = [m.wrap_objid[w] for w in range(m.tendon_adr[t], m.tendon_adr[t] + m.tendon_num[t])
                      if m.wrap_type[w] == int(mujoco.mjtWrap.mjWRAP_JOINT)]
        else:
            return None
        bodies = [m.jnt_bodyid[j] for j in joints]
        one = subtree(m, bodies[0])
        two = subtree(m, bodies[1]) if len(bodies) > 1 else {m.body_parentid[bodies[0]]}
        pick = lambda bs: [g for g in range(m.ngeom) if m.geom_bodyid[g] in bs and m.geom_contype[g]]
        return pick(one), pick(two)

    def gripper_gap(self, ctrl, steps=300):
        """Opening (m) at the grip point along the closing axis, like a caliper, with the gripper motor at `ctrl`."""
        m, r = self.model, self.robot
        d = mujoco.MjData(m)
        mujoco.mj_copyData(d, m, self.data)
        d.ctrl[self.gripper_ids[0]] = ctrl
        for _ in range(steps):
            mujoco.mj_step(m, d)
        rot = d.site_xmat[self.ee_site_id].reshape(3, 3)
        point = d.site_xpos[self.ee_site_id] + rot @ np.array(r.grip_offset)
        closing = rot @ _axis_vec(r.closing_axis)
        gap, hit, missed = 0.0, np.zeros(1, dtype=np.int32), False
        for direction in ((closing,) if r.fixed_jaw else (closing, -closing)):
            dist = mujoco.mj_ray(m, d, point, direction, None, 0, -1, hit)
            gap += dist if dist >= 0 else 0.15
            missed |= dist < 0
        sides = self._gripper_sides() if missed and not r.fixed_jaw else None
        if sides and sides[0] and sides[1]:  # fingertips closed past the grip point: the rays start inside a finger
            touch = min(mujoco.mj_geomDistance(m, d, a, b, 0.01, None) for a in sides[0] for b in sides[1])
            if touch < 0.005:
                return max(0.0, touch)
        return gap

    def _hand_geoms(self):
        """Collision geoms of the hand: everything below the body that carries the grip site."""
        m = self.model
        bodies = subtree(m, m.site_bodyid[self.ee_site_id])
        return [g for g in range(m.ngeom) if m.geom_bodyid[g] in bodies and m.geom_contype[g]]

    def measure_tip_reach(self, steps=300):
        """How far (m) the open fingers stick out past the grip point along the approach, measured from the
        collision shapes. The grip point must stay at least this high above the table."""
        m, r = self.model, self.robot
        geoms = self._hand_geoms()
        if self.ee_site_id is None or not geoms:
            return 0.0
        d = mujoco.MjData(m)
        mujoco.mj_copyData(d, m, self.data)
        d.ctrl[self.gripper_ids] = self.open_ctrl
        for _ in range(steps):
            mujoco.mj_step(m, d)
        rot = d.site_xmat[self.ee_site_id].reshape(3, 3)
        point = d.site_xpos[self.ee_site_id] + rot @ np.array(r.grip_offset)
        approach = rot @ _axis_vec(r.approach_axis)
        corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float)
        reach = 0.0
        for g in geoms:
            if m.geom_type[g] == int(mujoco.mjtGeom.mjGEOM_MESH):
                k = m.geom_dataid[g]
                local = m.mesh_vert[m.mesh_vertadr[k]:m.mesh_vertadr[k] + m.mesh_vertnum[k]]
            else:
                local = m.geom_aabb[g, :3] + corners * m.geom_aabb[g, 3:]
            pts = d.geom_xpos[g] + local @ d.geom_xmat[g].reshape(3, 3).T
            reach = max(reach, float(((pts - point) @ approach).max()))
        return reach

    @property
    def refusal(self):
        """(label, why) when this robot cannot do the card at all, measured; None when it can try."""
        if self.too_small:
            return "too_big", self.too_small
        if self.too_thin:
            return "too_thin", self.too_thin
        return self.needs_fail

    def measure_payload(self):
        """The heaviest object the arm can hold at its current pose (the ready pose after reset): for each arm joint,
        the torque limit minus what the arm's own weight already takes, over the extra torque per kg in the hand."""
        m, d = self.model, self.data
        d.qvel[:] = 0
        mujoco.mj_forward(m, d)
        jac = np.zeros((3, m.nv))
        mujoco.mj_jacSite(m, d, jac, None, self.ee_site_id)
        best = None
        for a in self.arm_actuators:
            if m.actuator_trntype[a] != int(mujoco.mjtTrn.mjTRN_JOINT):
                continue
            j = m.actuator_trnid[a, 0]
            if m.actuator_forcelimited[a]:
                limit = float(np.abs(m.actuator_forcerange[a]).max()) * abs(float(m.actuator_gear[a, 0]) or 1.0)
            elif m.jnt_actfrclimited[j]:
                limit = float(np.abs(m.jnt_actfrcrange[j]).max())
            else:
                continue
            dof = m.jnt_dofadr[j]
            per_kg = 9.81 * jac[2, dof]
            if abs(per_kg) < 1e-3:
                continue
            kg = (limit - np.sign(per_kg) * d.qfrc_bias[dof]) / abs(per_kg)
            best = kg if best is None else min(best, kg)
        return None if best is None else max(0.0, float(best))

    def fit_gripper(self, width, clearance=0.02):
        """Keep the adapter's open value when the object fits with `clearance` to spare, else open just wider.
        If the adapter's closed value does not even reach the object's width (a thin handle), close as far as the
        gripper goes; if no setting reaches it, the gripper cannot hold it (too_thin)."""
        self.open_ctrl = np.atleast_1d(self.robot.gripper_open).astype(float)
        self.close_ctrl = np.atleast_1d(self.robot.gripper_closed).astype(float)
        if self._gripper_sides() is None:
            return None
        lo, hi = self.model.actuator_ctrlrange[self.gripper_ids[0]]
        if self.gripper_gap(float(self.close_ctrl[0])) >= width:
            shut = {float(c): self.gripper_gap(c) for c in np.linspace(lo, hi, 25)}
            tightest = min(shut, key=shut.get)
            if shut[tightest] >= width:
                self.too_thin = (f"the gripper closes only to {shut[tightest] * 1000:.0f} mm, "
                                 f"the {self.objs['held']} is {width * 1000:.0f} mm thick")
            else:
                self.close_ctrl = np.array([tightest])
        need = width + clearance
        configured = float(self.open_ctrl[0])
        if self.gripper_gap(configured) >= need:
            return configured
        gaps = {float(c): self.gripper_gap(c) for c in np.linspace(lo, hi, 25)}
        widest = max(gaps.values())
        if widest < width:
            self.too_small = (f"the gripper opens at most {widest * 1000:.0f} mm, "
                              f"the {self.objs['held']} is {width * 1000:.0f} mm wide")
        wide = [c for c, g in gaps.items() if g >= need]
        chosen = min(wide, key=lambda c: abs(c - configured)) if wide else max(gaps, key=gaps.get)
        self.open_ctrl = np.array([chosen])
        return chosen

    def set_gripper(self, open_: bool):
        self.set_grip(0.0 if open_ else 1.0)

    def set_grip(self, closed: float):
        """0 = fully open, 1 = fully closed."""
        opened, shut = self.open_ctrl, self.close_ctrl
        self.data.ctrl[self.gripper_ids] = opened + closed * (shut - opened)

    def camera(self):
        """Overview camera; for an open card from behind the robot's right side, so the door is in view (a humanoid's
        back would hide it: from its right side instead). Carry: from in front of the robot, both tables in view."""
        cam = mujoco.MjvCamera()
        if self.kind == "carry":
            move = self.objs["move"]
            cam.lookat[:] = [self.base[0] + 0.1, self.base[1] + move / 2, TABLE_TOP + 0.05]
            cam.distance = 2.2 + 0.9 * abs(move)
            cam.azimuth, cam.elevation = 180 + math.copysign(20, move), -24
            return cam
        cam.lookat[:] = [self.origin[0] + 0.45 * self.reach, self.origin[1], TABLE_TOP + 0.12]
        cam.distance = 2.4 * self.reach + 0.35
        tall = self.origin[2] - TABLE_TOP > 0.3
        cam.azimuth, cam.elevation = ((100, -20) if tall else (35, -28)) if self.kind == "open" else (150, -28)
        return cam

    def ee_rot(self):
        return self.data.site_xmat[self.ee_site_id].reshape(3, 3).copy()

    def true_objects(self):
        """Object poses straight from the simulator (what the robot would see with perfect eyes)."""
        if self.kind == "open":
            return {self.objs["container"]: {"pos": self.bowl_pos(), "yaw": self.cabinet_yaw},
                    self.objs["held"]: {"pos": self.cube_pos(), "yaw": self.cabinet_yaw}}
        w, x, y, z = self.data.qpos[self.cube_qadr + 3:self.cube_qadr + 7]
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return {self.objs["held"]: {"pos": self.cube_pos(), "yaw": yaw}, self.objs["container"]: {"pos": self.bowl_pos()}}

    def bowl_pos(self):
        return self.model.body_pos[self.bowl_id].copy()

    def ee_pos(self):
        return self.data.site_xpos[self.ee_site_id].copy() if self.ee_site_id is not None else None

    def cube_pos(self):
        """The held object's position (an open card: the handle's)."""
        if self.kind == "open":
            return self.data.geom_xpos[self.handle_id].copy()
        return self.data.qpos[self.cube_qadr:self.cube_qadr + 3].copy()

    def door_angle(self):
        return float(self.data.qpos[self.door_qadr])

    def on_table(self, xy, margin):
        return all(abs(xy[i] - TABLE_CENTRE[i]) < TABLE_HALF[i] - margin for i in range(2))

    def cube_in_bowl(self):
        c = self.cube_pos()
        b = self.model.body_pos[self.bowl_id]
        inner = self.bowl_radius - float(self.objs["held_size"][0]) / 2
        off = np.abs(c[:2] - b[:2]).max() if self.square_bin else np.linalg.norm(c[:2] - b[:2])
        resting = c[2] < TABLE_TOP + max(self.bowl_wall, 0.021 + self.held_half)
        return bool(off < inner + 0.005 and resting)
