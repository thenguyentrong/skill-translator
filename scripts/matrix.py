"""Every skill in the library on every robot in the library: practice the grip, then N trials with camera vision.

Writes outputs/matrix/matrix.json, matrix.md (the table) and one video per cell (<skill>__<robot>.mp4).
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from translator.execute import FPS, run_skill
from translator.perceive import Eyes
from translator.practice import ensure
from translator.robots import ROBOTS
from translator.scene import TABLE_TOP, build, sample_layout

OUT = ROOT / "outputs" / "matrix"
CARDS = ROOT / "cards"


def cards(names=None):
    found = {p.stem: json.loads(p.read_text()) for p in sorted(CARDS.glob("*.json"))}
    return {n: found[n] for n in names} if names else found


def clip(scene, history, path, label, size=(480, 360)):
    m = scene.model
    d = mujoco.MjData(m)
    font = ImageFont.load_default(size=20)
    cam = scene.camera()
    note = "base slides, legs do not step" if scene.kind == "carry" and scene.robot.mobile else ""
    if scene.kind != "carry":  # a carry camera already frames both tables
        tall = max(0.0, scene.origin[2] - TABLE_TOP - 0.3)
        cam.distance = 1.5 * scene.reach + 0.35 + 1.6 * tall
        cam.lookat[:] = [scene.origin[0] + 0.5 * scene.reach, scene.origin[1], cam.lookat[2] + 0.5 * tall]
    with mujoco.Renderer(m, size[1], size[0]) as r:
        frames = []
        for q in history[::2]:
            d.qpos[:] = q
            mujoco.mj_forward(m, d)
            r.update_scene(d, camera=cam)
            im = Image.fromarray(r.render())
            draw = ImageDraw.Draw(im)
            draw.text((10, 8), label, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
            if note:
                draw.text((10, size[1] - 30), note, fill=(255, 200, 80), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
            frames.append(np.asarray(im))
    imageio.mimsave(path, frames, fps=FPS / 2, codec="libx264", quality=7, macro_block_size=8)


def cell(job):
    skill, card, robot, n, seed, video = job
    t0 = time.time()
    scene = build(robot, card)
    if scene.refusal:
        label, why = scene.refusal
        return {"skill": skill, "robot": robot, "success": 0, "n": n, "fails": {label: n}, "why": why,
                "grip_depth_mm": 0, "seconds": round(time.time() - t0, 1)}
    try:
        sample_layout(scene, np.random.default_rng(seed))
    except (RuntimeError, ValueError) as e:
        return {"skill": skill, "robot": robot, "success": 0, "n": n, "fails": {"no_room": n}, "why": str(e),
                "grip_depth_mm": 0, "seconds": round(time.time() - t0, 1)}
    eyes = Eyes(scene)
    reasons = []
    for i in range(n):
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed + i))
        scene.reset(cube, bowl, yaw)
        seen = eyes.find(card)
        if any(v is None for v in seen.values()):
            reasons.append("unseen")
            continue
        try:
            res = run_skill(scene, card, seen)
        except Exception as e:
            reasons.append(f"error: {e}"[:60])
            continue
        reasons.append(res.reason)
        if video and i == 0:
            clip(scene, res.history, OUT / f"{skill}__{robot}.mp4", f"{robot}: {skill}  ({'ok' if res.success else res.reason})")
        if video == "fail" and not res.success and sum(r != "ok" for r in reasons) == 1:
            clip(scene, res.history, OUT / f"{skill}__{robot}_fail.mp4", f"{robot}: {skill}  ({res.reason})")
    eyes.close()
    fails = {}
    for r in reasons:
        if r != "ok":
            fails[r] = fails.get(r, 0) + 1
    return {"skill": skill, "robot": robot, "success": reasons.count("ok"), "n": n, "fails": fails,
            "grip_depth_mm": round(scene.grip_depth * 1000), "seconds": round(time.time() - t0, 1)}


REFUSALS = ("too_big", "too_thin", "no_room", "two_hands", "must_walk", "too_heavy", "two_hand_grip", "handle_too_high",
            "handle_too_low")


def table(rows, skills, robots):
    by = {(r["skill"], r["robot"]): r for r in rows}
    lines = ["| skill \\ robot | " + " | ".join(robots) + " |", "|---|" + "---|" * len(robots)]
    for s in skills:
        cells = []
        for rb in robots:
            r = by.get((s, rb))
            whole = next((k for k, v in r["fails"].items() if v == r["n"] and k in REFUSALS), None) if r else None
            cells.append("-" if not r else whole.replace("_", " ") if whole else f"{r['success']}/{r['n']}")
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--skills", nargs="*", help="card names in cards/ (default: all)")
    p.add_argument("--robots", nargs="*", help="robot names (default: the whole library)")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--merge", action="store_true", help="keep the other cells of the last matrix.json")
    args = p.parse_args()
    skills = cards(args.skills)
    robots = args.robots or [n for n in ROBOTS if not n.endswith("_muse")]
    OUT.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    practice = {}
    for s, card in skills.items():
        for r in robots:
            pr = ensure(r, card)
            practice[f"{s}__{r}"] = pr
            print(f"practice {s:15s} {r:8s} grip depth {pr['grip_depth'] * 1000:+4.0f} mm  {pr['success']}/{pr['n']}", flush=True)
    t_practice = time.time() - t0

    jobs = [(s, card, r, args.n, args.seed, not args.no_video) for s, card in skills.items() for r in robots]
    with Pool(min(args.workers, len(jobs))) as pool:
        rows = []
        for row in pool.imap_unordered(cell, jobs):
            rows.append(row)
            print(f"{row['skill']:15s} {row['robot']:8s} {row['success']}/{row['n']}  {row['fails'] or ''}  ({row['seconds']} s)", flush=True)
    skill_names, robot_names = list(skills), list(robots)
    if args.merge and (OUT / "matrix.json").exists():
        old = json.loads((OUT / "matrix.json").read_text())
        done = {(r["skill"], r["robot"]) for r in rows}
        rows += [r for r in old["rows"] if (r["skill"], r["robot"]) not in done]
        skill_names = list(dict.fromkeys(old.get("skills", []) + skill_names))
        robot_names = list(dict.fromkeys(old.get("robots", []) + robot_names))
        practice = {**old.get("practice", {}), **practice}
    md = table(rows, skill_names, robot_names)
    (OUT / "matrix.json").write_text(json.dumps({"skills": skill_names, "robots": robot_names, "rows": rows,
                                                  "practice": practice, "seed": args.seed, "n": args.n,
                                                  "practice_seconds": round(t_practice, 1),
                                                  "seconds": round(time.time() - t0, 1)}, indent=1))
    (OUT / "matrix.md").write_text(md + "\n")
    print()
    print(md)
    print(f"\npractice {t_practice:.0f} s, total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
