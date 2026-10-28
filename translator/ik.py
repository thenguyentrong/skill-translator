"""Inverse kinematics for the end-effector site with mink. Only the robot's active arm joints move."""
import mink
import mujoco
import numpy as np

from .scene import PREFIX, Scene, subtree as _subtree


def _self_collision_pair(scene: Scene):
    """Forearm and hand (from the 4th arm joint on) against the robot parts the arm does not move."""
    m = scene.model
    if len(scene.arm_joints) < 4:
        return None
    arm = _subtree(m, m.jnt_bodyid[scene.arm_joints[0]])
    distal = _subtree(m, m.jnt_bodyid[scene.arm_joints[3]])
    robot = [g for g in range(m.ngeom) if m.geom_contype[g] and m.body(m.geom_bodyid[g]).name.startswith(PREFIX)]
    near = [g for g in robot if m.geom_bodyid[g] in distal]
    rest = [g for g in robot if m.geom_bodyid[g] not in arm]
    return (near, rest) if near and rest else None


def _furniture_pair(scene: Scene):
    """Open cards: the arm (not the hand) against the table top and the cabinet body, so a sideways grip does not
    put the wrist through the table."""
    m = scene.model
    if not scene.arm_joints:
        return None
    hand = _subtree(m, m.site_bodyid[scene.ee_site_id])
    furniture = [m.geom("table_top").id, m.geom("cabinet").id]
    d = scene._home_data()
    mujoco.mj_forward(m, d)
    clear = lambda g: all(mujoco.mj_geomDistance(m, d, g, f, 0.05, None) > 0.02 for f in furniture)
    arm = [g for g in range(m.ngeom) if m.geom_contype[g] and m.geom_bodyid[g] in _subtree(m, m.jnt_bodyid[scene.arm_joints[0]])
           and m.geom_bodyid[g] not in hand and clear(g)]
    return (arm, furniture) if arm else None


class HandsIK:
    """IK for one or two hands at once (carry): each hand's site gets a target, only those arms' joints move, each
    arm keeps 2 cm from the rest of the robot and from the other arm. The start pose is clipped into the joint
    limits first (the QP has no solution from outside them)."""

    def __init__(self, scene: Scene, hands, orientation_cost=0.3):
        m = scene.model
        self.scene, self.hands = scene, hands
        self.cfg = mink.Configuration(m)
        self.tasks = [mink.FrameTask(m.site(h.site).name, "site", position_cost=1.0, orientation_cost=orientation_cost,
                                     lm_damping=1e-3) for h in hands]
        self.posture = mink.PostureTask(m, cost=1e-2)
        dofs = {int(m.jnt_dofadr[j]) for h in hands for j in h.joints}
        self.constraints = [mink.DofFreezingTask(m, dof_indices=[i for i in range(m.nv) if i not in dofs])]
        robot = [g for g in range(m.ngeom) if m.geom_contype[g] and m.body(m.geom_bodyid[g]).name.startswith(PREFIX)]
        whole = set().union(*(_subtree(m, m.jnt_bodyid[h.joints[0]]) for h in hands))
        arms = [[g for g in robot if m.geom_bodyid[g] in _subtree(m, m.jnt_bodyid[h.joints[1]])] for h in hands]
        rest = [g for g in robot if m.geom_bodyid[g] not in whole]
        pairs = [(a, rest) for a in arms if a and rest] + ([(arms[0], arms[1])] if len(arms) == 2 and all(arms) else [])
        self.limits = [mink.ConfigurationLimit(m)]
        if pairs:
            self.limits.append(mink.CollisionAvoidanceLimit(m, pairs, minimum_distance_from_collisions=0.02,
                                                            collision_detection_distance=0.08))
        self.sites_z = [0.0] * len(hands)

    def solve(self, qpos, targets, iters=120, dt=0.02):
        """targets: (pos, rot) per hand. Returns the arm angles per hand and each hand's miss (m)."""
        m = self.scene.model
        q0 = qpos.copy()
        for j in range(m.njnt):
            if m.jnt_limited[j] and m.jnt_type[j] in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                a = m.jnt_qposadr[j]
                q0[a] = np.clip(q0[a], m.jnt_range[j][0] + 1e-3, m.jnt_range[j][1] - 1e-3)
        self.cfg.update(q0)
        self.posture.set_target(q0)
        for t, (pos, rot) in zip(self.tasks, targets):
            t.set_target(mink.SE3.from_rotation_and_translation(mink.SO3.from_matrix(rot), pos))
        for _ in range(iters):
            try:
                v = mink.solve_ik(self.cfg, self.tasks + [self.posture], dt, "daqp", damping=1e-3, limits=self.limits,
                                  constraints=self.constraints)
            except mink.exceptions.NoSolutionFound:
                v = mink.solve_ik(self.cfg, self.tasks + [self.posture], dt, "daqp", damping=1e-3, limits=self.limits[:1],
                                  constraints=self.constraints)
            self.cfg.integrate_inplace(v, dt)
        d = self.cfg.data
        self.sites_z = [float(d.site_xpos[h.site][2]) for h in self.hands]
        errs = [float(np.linalg.norm(d.site_xpos[h.site] - p)) for h, (p, _) in zip(self.hands, targets)]
        return [self.cfg.q[h.qadr].copy() for h in self.hands], errs


class IK:
    def __init__(self, scene: Scene, posture_cost=1e-2, damping_cost=0.1):
        m = scene.model
        self.scene = scene
        self.cfg = mink.Configuration(m, scene.data.qpos.copy())
        self.frame = mink.FrameTask(PREFIX + scene.robot.ee_site, "site", position_cost=1.0,
                                    orientation_cost=scene.robot.orientation_cost, lm_damping=1e-3)
        self.posture = mink.PostureTask(m, cost=posture_cost)
        self.posture.set_target(scene.data.qpos.copy())
        self.damping = mink.DampingTask(m, cost=damping_cost)
        arm_dofs = {int(m.jnt_dofadr[j]) for j in scene.arm_joints}
        self.constraints = [mink.DofFreezingTask(m, dof_indices=[i for i in range(m.nv) if i not in arm_dofs])]
        speed = {m.joint(j).name: scene.robot.max_joint_speed for j in scene.arm_joints}
        self.limits = [mink.ConfigurationLimit(m), mink.VelocityLimit(m, speed)]
        pairs = [p for p in (_self_collision_pair(scene), _furniture_pair(scene) if scene.kind == "open" else None) if p]
        if pairs:
            self.limits.append(mink.CollisionAvoidanceLimit(m, pairs, minimum_distance_from_collisions=0.01,
                                                            collision_detection_distance=0.05))
        self.arm_qadr = [int(m.jnt_qposadr[j]) for j in scene.arm_joints]
        self.site_id = scene.ee_site_id
        r = scene.robot
        self.free_axis = 3 - "xyz".index(r.approach_axis[1]) - "xyz".index(r.closing_axis[1])

    def reach(self, pos, rot, tries=12, seed=0):
        """Joint pose for a far target: settle the IK from the current pose and from a few random arm poses near it,
        keep the best (least error, then least joint travel). Sets the IK's own state to it."""
        q0 = self.cfg.q.copy()
        rng = np.random.default_rng(seed)
        m = self.scene.model
        best = None
        for k in range(tries):
            q = q0.copy()
            if k:
                for j, a in zip(self.scene.arm_joints, self.arm_qadr):
                    lo, hi = m.jnt_range[j] if m.jnt_limited[j] else (-np.pi, np.pi)
                    q[a] = np.clip(q0[a] + rng.uniform(-1.2, 1.2), lo, hi)
            self.cfg.update(q)
            for _ in range(30):
                qa, pe, re = self.solve(pos, rot, 0.25)
            score = (round(pe, 3), round(re, 2), float(np.abs(qa - q0[self.arm_qadr]).sum()))
            if best is None or score < best[0]:
                best = (score, self.cfg.q.copy(), qa, pe, re)
        self.cfg.update(best[1])
        return best[2], best[3], best[4]

    def solve(self, pos, rot, duration, iters=10, tol=5e-4, free_turn=False):
        """Move towards the target for `duration` seconds; joint speeds stay under the robot's limit. `free_turn`:
        turning about the hand's third axis (across both approach and closing, e.g. along a bar held in the
        fingers) costs almost nothing."""
        cost = np.full(3, self.scene.robot.orientation_cost)
        if free_turn:
            cost[self.free_axis] *= 0.05
        self.frame.set_orientation_cost(cost)
        self.frame.set_target(mink.SE3.from_rotation_and_translation(mink.SO3.from_matrix(rot), pos))
        dt = duration / iters
        for _ in range(iters):
            vel = mink.solve_ik(self.cfg, [self.frame, self.posture, self.damping], dt, "daqp", damping=1e-3,
                                limits=self.limits, constraints=self.constraints)
            self.cfg.integrate_inplace(vel, dt)
            err = self.frame.compute_error(self.cfg)
            if free_turn:
                err[3 + self.free_axis] = 0.0
            if np.linalg.norm(err[:3]) < tol and np.linalg.norm(err[3:]) < 10 * tol:
                break
        d = self.cfg.data
        pos_err = float(np.linalg.norm(d.site_xpos[self.site_id] - pos))
        r = d.site_xmat[self.site_id].reshape(3, 3)
        rot_err = float(np.arccos(np.clip((np.trace(rot.T @ r) - 1) / 2, -1.0, 1.0)))
        if free_turn:
            rot_err = float(np.arccos(np.clip(np.dot(rot[:, self.free_axis], r[:, self.free_axis]), -1.0, 1.0)))
        return self.cfg.q[self.arm_qadr].copy(), pos_err, rot_err
