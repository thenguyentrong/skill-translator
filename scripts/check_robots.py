"""Loads every robot into the scene, moves each joint and the gripper, renders a contact sheet."""
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mujoco
import numpy as np
from PIL import Image

from translator.robots import ROBOTS
from translator.render import Cameras
from translator.scene import build

OUT = Path(__file__).resolve().parents[1] / "outputs" / "check"
W, H = 480, 360


def run(scene, seconds):
    for _ in range(int(seconds / scene.model.opt.timestep)):
        mujoco.mj_step(scene.model, scene.data)


def joint_q(scene, a):
    m = scene.model
    return scene.data.qpos[m.jnt_qposadr[m.actuator_trnid[a, 0]]]


def check(name, renderer_cache):
    s = build(name)
    m, d = s.model, s.data
    if name not in renderer_cache:
        renderer_cache[name] = mujoco.Renderer(m, H, W)
    r = renderer_cache[name]
    cam = s.camera()
    frames = []

    def snap():
        r.update_scene(d, camera=cam)
        frames.append(r.render().copy())

    run(s, 1.0)
    snap()
    drift = float(np.max(np.abs(d.qvel[: m.nv - 6]))) if m.nv > 6 else 0.0

    home_ctrl = d.ctrl.copy()
    start = mujoco.MjData(m)
    mujoco.mj_copyData(start, m, d)
    errs = None
    for step in (0.3, -0.3):
        mujoco.mj_copyData(d, m, start)
        for a in s.arm_actuators:
            lo, hi = m.actuator_ctrlrange[a]
            target = float(np.clip(home_ctrl[a] + step, lo, hi))
            if abs(target - home_ctrl[a]) < 1e-6:
                target = float(np.clip(home_ctrl[a] - step, lo, hi))
            d.ctrl[a] = target
        run(s, 1.5)
        trial = [abs(joint_q(s, a) - d.ctrl[a]) for a in s.arm_actuators]
        if errs is None or max(trial) < max(errs):
            errs, moved = trial, d.qpos.copy()
        if max(errs) < 0.06:
            break
    d.qpos[:] = moved
    mujoco.mj_forward(m, d)
    snap()
    d.ctrl[:] = home_ctrl
    run(s, 1.5)

    grip = None
    if s.gripper_ids:
        others = {m.actuator_trnid[a, 0] for a in range(m.nu) if a not in s.gripper_ids}
        gj = [m.jnt_qposadr[j] for j in s.joints if j not in others]
        q0 = d.qpos[gj].copy()
        s.set_gripper(open_=False)
        run(s, 1.0)
        snap()
        grip = float(np.max(np.abs(d.qpos[gj] - q0)))
        s.set_gripper(open_=True)
        run(s, 1.0)
    snap()

    ok = bool(np.all(np.isfinite(d.qpos))) and max(errs) < 0.06 and (grip is None or grip > 0.01)
    cams = Cameras(m)
    frames.append(cams.column(d))
    cams.close()
    print(f"{name:6s} nq={m.nq:3d} nu={m.nu:2d} reach={s.reach:.2f} m settle_qvel={drift:.3f} "
          f"max_track_err={max(errs):.3f} rad gripper_move={'-' if grip is None else f'{grip:.3f}'} "
          f"cube={np.round(s.cube_pos(), 3).tolist()} -> {'OK' if ok else 'FAIL'}")
    return frames, ok


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(ROBOTS)
    cache, rows, cam_rows, all_ok = {}, [], [], True
    for name in names:
        frames, ok = check(name, cache)
        all_ok &= ok
        cam_rows.append(np.concatenate(np.split(frames.pop(), 3, axis=0), axis=1))
        while len(frames) < 4:
            frames.append(np.zeros_like(frames[0]))
        rows.append(np.concatenate(frames, axis=1))
    for r in cache.values():
        r.close()
    Image.fromarray(np.concatenate(rows, axis=0)).save(OUT / "robots.png")
    Image.fromarray(np.concatenate(cam_rows, axis=0)).save(OUT / "cameras.png")
    print("saved", OUT / "robots.png", "and", OUT / "cameras.png")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
