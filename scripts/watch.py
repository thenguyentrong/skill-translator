"""Live view: any robot from the library does any skill from the library, in the MuJoCo viewer, in real time.

  watch.py                                  # the four hand-written robots, cube_to_bowl
  watch.py tienkung3 xarm7 --skill lemon_to_bowl can_to_bin
  watch.py robots/muse/lite6.json --skill block_to_plate
  watch.py --list                           # what is in the robot and skill libraries
Close the window to stop."""
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

from translator.execute import FPS, run_skill
from translator.perceive import Eyes
from translator.render import Cameras
from translator.practice import ensure
from translator.robots import ROBOTS
from translator.scene import TABLE_TOP, build, sample_layout
from translator.translate import load_card

CARDS = ROOT / "cards"


class Closed(Exception):
    pass


def watch_robot(name, card, seeds, speed):
    ensure(name, card)
    scene = build(name, card)
    held = card["grip"]["object"]
    done = ("door open" if card.get("kind") == "open" else f"{held} on {card['success']['place']}" if card.get("kind") == "carry"
            else f"{held} in {card['success']['container']}")
    cams = Cameras(scene.model, 320, 240)
    eyes = Eyes(scene)
    score = [0, 0]
    with mujoco.viewer.launch_passive(scene.model, scene.data, show_left_ui=False, show_right_ui=False) as viewer:
        cam = viewer.cam
        cam.lookat[:] = [scene.origin[0] + 0.45 * scene.reach, scene.origin[1], TABLE_TOP + 0.08]
        cam.distance = 1.9 * scene.reach + 0.25
        cam.azimuth, cam.elevation = 145, -25
        if scene.kind == "carry":  # both tables in view
            c = scene.camera()
            cam.lookat[:], cam.distance, cam.azimuth, cam.elevation = c.lookat, c.distance, c.azimuth, c.elevation
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
                                  "Robot\nSkill\nTrial\nStep\nScore\n" + ("Result" if result else ""),
                                  f"{name}\n{card['name']}\nseed {seed}\n{step}\n{score[0]}/{score[1]}\n{result}"))

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
            show("done", f"OK: {done}" if res.success else f"FAIL: {res.reason}")
            viewer.sync()
            print(f"{name} {card['name']} seed {seed}: {'OK' if res.success else 'FAIL ' + res.reason}", flush=True)
            time.sleep(1.5)
    cams.close()
    eyes.close()
    return score


def main():
    p = argparse.ArgumentParser()
    p.add_argument("robots", nargs="*", default=["so101", "panda", "ur5e", "g1"], help="names or adapter files")
    p.add_argument("--skill", nargs="+", default=["cube_to_bowl"], help="skill names in cards/ (or card files)")
    p.add_argument("--trials", type=int, default=3, help="trials per robot and skill before switching")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--speed", type=float, default=1.0, help="1.0 = real time")
    p.add_argument("--once", action="store_true", help="stop after one round instead of looping")
    p.add_argument("--list", action="store_true", help="show the robot and skill libraries and stop")
    args = p.parse_args()
    if args.list:
        print("robots:", ", ".join(f"{n} ({r.source})" for n, r in ROBOTS.items()))
        print("skills:", ", ".join(c.stem for c in sorted(CARDS.glob("*.json"))))
        return
    cards = [load_card(c if c.endswith(".json") else CARDS / f"{c}.json") for c in args.skill]
    seed = args.seed
    try:
        while True:
            for card in cards:
                for name in args.robots:
                    watch_robot(name, card, range(seed, seed + args.trials), args.speed)
            seed += args.trials
            if args.once:
                break
    except Closed:
        print("viewer closed", flush=True)


if __name__ == "__main__":
    main()
