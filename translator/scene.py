"""Tabletop scene: table, 3 cm cube, bowl and one robot."""
import math

import mujoco
import numpy as np

from .robots import ROBOTS, Robot

TABLE_TOP = 0.75
CUBE_HALF = 0.015
BOWL_RADIUS = 0.06
BOWL_WALL = 0.04
TABLE_CENTRE = (0.35, 0.0)
TABLE_HALF = (0.55, 0.6)
PREFIX = "robot/"
CAMERAS = ("front", "top", PREFIX + "wrist")

_MOVABLE = (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))


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


def _robot_spec(robot: Robot):
    home = _key_home(robot.xml, robot.home) if isinstance(robot.home, str) else dict(robot.home or {})
    home.update(robot.ready or {})
    spec = mujoco.MjSpec.from_file(str(robot.xml))
    for key in list(spec.keys):
        spec.delete(key)
    if robot.ee_add:
        body, pos = robot.ee_add
        spec.body(body).add_site(name=robot.ee_site, pos=pos, group=3)
    if robot.tool:
        site, xml = robot.tool
        tool = mujoco.MjSpec.from_file(str(xml))
        spec.option.cone, spec.option.impratio = tool.option.cone, tool.option.impratio
        spec.site(site).attach_body(tool.worldbody.first_body(), "tool/", "")
    if robot.fixed_base:
        for j in list(spec.worldbody.first_body().joints):
            if j.type == mujoco.mjtJoint.mjJNT_FREE:
                spec.delete(j)
    if robot.ee_site:
        _add_wrist_camera(spec, robot)
    return spec, home


def _add_bowl(world):
    bowl = world.add_body(name="bowl", pos=[0.4, -0.2, TABLE_TOP])
    color = [0.25, 0.62, 0.35, 1]
    bowl.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[BOWL_RADIUS + 0.005, 0.003, 0], pos=[0, 0, 0.003], rgba=color)
    n = 20
    half_len = (BOWL_RADIUS + 0.005) * math.tan(math.pi / n)
    for i in range(n):
        a = 2 * math.pi * i / n
        bowl.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=[0.003, half_len, BOWL_WALL / 2],
            pos=[(BOWL_RADIUS + 0.003) * math.cos(a), (BOWL_RADIUS + 0.003) * math.sin(a), BOWL_WALL / 2],
            quat=[math.cos(a / 2), 0, 0, math.sin(a / 2)],
            rgba=color,
        )


def build(name: str):
    robot = ROBOTS[name]
    spec = mujoco.MjSpec()
    spec.modelname = f"scene_{name}"
    spec.option.timestep = 0.002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.impratio = 10
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    spec.visual.headlight.diffuse = [0.5, 0.5, 0.5]
    spec.visual.headlight.ambient = [0.3, 0.3, 0.3]

    world = spec.worldbody
    world.add_light(pos=[0.3, -0.5, 2.5], dir=[0, 0.2, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=True)
    world.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.05], rgba=[0.35, 0.37, 0.4, 1])
    table = world.add_body(name="table", pos=[TABLE_CENTRE[0], TABLE_CENTRE[1], TABLE_TOP])
    table.add_geom(name="table_top", type=mujoco.mjtGeom.mjGEOM_BOX, size=[TABLE_HALF[0], TABLE_HALF[1], 0.02], pos=[0, 0, -0.02],
                   rgba=[0.62, 0.5, 0.38, 1])
    for sx in (-1, 1):
        for sy in (-1, 1):
            table.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.025, 0.025, (TABLE_TOP - 0.04) / 2],
                           pos=[sx * (TABLE_HALF[0] - 0.05), sy * (TABLE_HALF[1] - 0.05), -0.04 - (TABLE_TOP - 0.04) / 2],
                           rgba=[0.45, 0.36, 0.27, 1])

    cube = world.add_body(name="cube", pos=[0.4, 0.2, TABLE_TOP + CUBE_HALF])
    cube.add_freejoint(name="cube")
    cube.add_geom(name="cube", type=mujoco.mjtGeom.mjGEOM_BOX, size=[CUBE_HALF] * 3, mass=0.03,
                  friction=[1.0, 0.005, 0.0001], condim=4, rgba=[0.85, 0.2, 0.15, 1])
    _add_bowl(world)

    rspec, home = _robot_spec(robot)
    yaw = robot.base_yaw
    base = np.array([robot.base_pos[0], robot.base_pos[1], TABLE_TOP + robot.base_pos[2]])
    frame = world.add_frame(pos=base, quat=[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)])
    frame.attach_body(rspec.worldbody.first_body(), PREFIX, "")

    model = spec.compile()
    probe = Scene(robot, model, mujoco.MjData(model), home, base)
    _add_world_cameras(world, probe.origin, probe.reach)
    model = spec.compile()
    scene = Scene(robot, model, mujoco.MjData(model), home, base, probe.reach, probe.footprint)
    scene.reset()
    return scene


class Scene:
    def __init__(self, robot: Robot, model, data, home, base, reach=None, footprint=None):
        self.robot, self.model, self.data, self.base = robot, model, data, base
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
        self.arm_joints = [model.actuator_trnid[a, 0] for a in self.arm_actuators
                           if model.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
        self.ee_site_id = model.site(PREFIX + robot.ee_site).id if robot.ee_site else None
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
        return float(np.percentile(dist, 90))

    def _robot_boxes(self, below=0.08):
        """Robot collision boxes (xy bounds) that sit on the table, up to `below` above it, at home.
        Splits them into parts that turn with the arm's first joint and parts that stay put."""
        m, d = self.model, self._home_data()
        first = m.jnt_bodyid[self.arm_joints[0]] if self.arm_joints else -1
        turning, fixed = [], []
        for g in range(m.ngeom):
            b = m.geom_bodyid[g]
            if not m.geom_contype[g] or not m.body(b).name.startswith(PREFIX):
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
        """Cube on the left, bowl on the right, both well inside the reach."""
        x = self.origin[0] + 0.55 * self.reach
        dy = 0.3 * self.reach
        return (x, self.origin[1] + dy), (x, self.origin[1] - dy)

    def reset(self, cube_xy=None, bowl_xy=None, cube_yaw=0.0):
        m, d = self.model, self.data
        cube_default, bowl_default = self.default_layout()
        cube_xy = cube_default if cube_xy is None else cube_xy
        bowl_xy = bowl_default if bowl_xy is None else bowl_xy
        mujoco.mj_resetData(m, d)
        for j in self.joints:
            d.qpos[m.jnt_qposadr[j]] = self.home.get(m.joint(j).name, 0.0)
        d.qpos[self.cube_qadr:self.cube_qadr + 7] = [cube_xy[0], cube_xy[1], TABLE_TOP + CUBE_HALF,
                                                       math.cos(cube_yaw / 2), 0, 0, math.sin(cube_yaw / 2)]
        m.body_pos[self.bowl_id] = [bowl_xy[0], bowl_xy[1], TABLE_TOP]
        mujoco.mj_forward(m, d)
        for a in range(m.nu):
            if a not in self.gripper_ids and m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT):
                d.ctrl[a] = d.qpos[m.jnt_qposadr[m.actuator_trnid[a, 0]]]
        self.set_gripper(open_=True)

    def set_gripper(self, open_: bool):
        self.set_grip(0.0 if open_ else 1.0)

    def set_grip(self, closed: float):
        """0 = fully open, 1 = fully closed."""
        r = self.robot
        opened, shut = np.atleast_1d(r.gripper_open), np.atleast_1d(r.gripper_closed)
        self.data.ctrl[self.gripper_ids] = opened + closed * (shut - opened)

    def camera(self):
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [self.origin[0] + 0.45 * self.reach, self.origin[1], TABLE_TOP + 0.12]
        cam.distance = 2.4 * self.reach + 0.35
        cam.azimuth, cam.elevation = 150, -28
        return cam

    def ee_rot(self):
        return self.data.site_xmat[self.ee_site_id].reshape(3, 3).copy()

    def true_objects(self):
        """Object poses straight from the simulator (what the robot would see with perfect eyes)."""
        w, x, y, z = self.data.qpos[self.cube_qadr + 3:self.cube_qadr + 7]
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return {"cube": {"pos": self.cube_pos(), "yaw": yaw}, "bowl": {"pos": self.bowl_pos()}}

    def bowl_pos(self):
        return self.model.body_pos[self.bowl_id].copy()

    def ee_pos(self):
        return self.data.site_xpos[self.ee_site_id].copy() if self.ee_site_id is not None else None

    def cube_pos(self):
        return self.data.qpos[self.cube_qadr:self.cube_qadr + 3].copy()

    def on_table(self, xy, margin):
        return all(abs(xy[i] - TABLE_CENTRE[i]) < TABLE_HALF[i] - margin for i in range(2))

    def cube_in_bowl(self):
        c = self.cube_pos()
        b = self.model.body_pos[self.bowl_id]
        return bool(np.linalg.norm(c[:2] - b[:2]) < BOWL_RADIUS - CUBE_HALF and c[2] < TABLE_TOP + BOWL_WALL)
