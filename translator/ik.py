"""Inverse kinematics for the end-effector site with mink. Only the robot's active arm joints move."""
import mink
import numpy as np

from .scene import PREFIX, Scene


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
        self.arm_qadr = [int(m.jnt_qposadr[j]) for j in scene.arm_joints]
        self.site_id = scene.ee_site_id

    def solve(self, pos, rot, duration, iters=10, tol=5e-4):
        """Move towards the target for `duration` seconds; joint speeds stay under the robot's limit."""
        self.frame.set_target(mink.SE3.from_rotation_and_translation(mink.SO3.from_matrix(rot), pos))
        dt = duration / iters
        for _ in range(iters):
            vel = mink.solve_ik(self.cfg, [self.frame, self.posture, self.damping], dt, "daqp", damping=1e-3,
                                limits=self.limits, constraints=self.constraints)
            self.cfg.integrate_inplace(vel, dt)
            err = self.frame.compute_error(self.cfg)
            if np.linalg.norm(err[:3]) < tol and np.linalg.norm(err[3:]) < 10 * tol:
                break
        d = self.cfg.data
        pos_err = float(np.linalg.norm(d.site_xpos[self.site_id] - pos))
        r = d.site_xmat[self.site_id].reshape(3, 3)
        rot_err = float(np.arccos(np.clip((np.trace(rot.T @ r) - 1) / 2, -1.0, 1.0)))
        return self.cfg.q[self.arm_qadr].copy(), pos_err, rot_err
