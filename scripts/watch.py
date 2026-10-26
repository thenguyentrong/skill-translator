"""Live view: runs the skill card on random layouts in the MuJoCo viewer, in real time. Close the window to stop."""
import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mujoco
import mujoco.viewer
import numpy as np

from kill_test import sample_layout
from translator.execute import FPS, run_skill
from translator.perceive import Eyes
from translator.render import Cameras
from translator.scene import TABLE_TOP, build
from translator.translate import load_card


class Closed(Exception):
    pass


def watch_robot(name, card, seeds, speed):
    scene = build(name)
    cams = Cameras(scene.model, 320, 240)
    eyes = Eyes(scene)
    score = [0, 0]
    with mujoco.viewer.launch_passive(scene.model, scene.data, show_left_ui=False, show_right_ui=False) as viewer:
        cam = viewer.cam
        cam.lookat[:] = [scene.origin[0] + 0.45 * scene.reach, scene.origin[1], TABLE_TOP + 0.08]
        cam.distance = 1.9 * scene.reach + 0.25
        cam.azimuth, cam.elevation = 145, -25
        for seed in seeds:
            cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
            with viewer.lock():
                scene.reset(cube, bowl, yaw)
            clock = [time.perf_counter()]

            def show_cameras():
                vp = viewer.viewport
                if vp is None:
                    return
                views = cams.views(scene.data).values()
                viewer.set_images([(mujoco.MjrRect(vp.width - 330, 10 + i * 250, 320, 240), img)
                                   for i, img in enumerate(reversed(list(views)))])

            def show(step, result=""):
                viewer.set_texts((mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                                  "Robot\nTrial\nStep\nScore\n" + ("Result" if result else ""),
                                  f"{name}\nseed {seed}\n{step}\n{score[0]}/{score[1]}\n{result}"))

            def on_tick(label):
                if not viewer.is_running():
                    raise Closed
                show(label)
                show_cameras()
                viewer.sync()
                clock[0] += 1 / FPS / speed
                time.sleep(max(0.0, clock[0] - time.perf_counter()))

            show("start")
            viewer.sync()
            time.sleep(0.8)
            seen = eyes.find(card)
            if any(v is None for v in seen.values()):
                print(f"{name} seed {seed}: cannot see every object, skipped", flush=True)
                continue
            res = run_skill(scene, card, seen, on_tick=on_tick)
            score[0] += res.success
            score[1] += 1
            show("done", "OK: cube in bowl" if res.success else f"FAIL: {res.reason}")
            viewer.sync()
            print(f"{name} seed {seed}: {'OK' if res.success else 'FAIL ' + res.reason}", flush=True)
            time.sleep(1.5)
    cams.close()
    eyes.close()
    return score


def main():
    p = argparse.ArgumentParser()
    p.add_argument("robots", nargs="*", default=["so101", "panda", "ur5e", "g1"])
    p.add_argument("--trials", type=int, default=3, help="trials per robot before switching")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--speed", type=float, default=1.0, help="1.0 = real time")
    p.add_argument("--once", action="store_true", help="stop after one round instead of looping")
    p.add_argument("--card", default=str(ROOT / "cards" / "cube_to_bowl.json"))
    args = p.parse_args()
    card = load_card(args.card)
    seed = args.seed
    try:
        while True:
            for name in args.robots:
                watch_robot(name, card, range(seed, seed + args.trials), args.speed)
            seed += args.trials
            if args.once:
                break
    except Closed:
        print("viewer closed", flush=True)


if __name__ == "__main__":
    main()
