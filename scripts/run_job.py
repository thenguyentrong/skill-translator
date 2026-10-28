"""One job: a short video of a task -> skill card (SAM 3.1 + Muse Spark) -> each robot tries it in simulation.

Writes outputs/jobs/<video name>/: names.json, tracks.json, tracks_overlay.mp4, events.json, card_muse.json,
card.json, <robot>_trial0.mp4 and report.json with the time and cost of every stage.
--check stops before any try: each robot only says if it can do the card (seconds, no compute), so a user can pick.
--train then makes a dataset, trains and tests a policy for every robot that passed (scripts/train_job.py).
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from kill_test import save_video
from make_reel import make as make_reel
from track_video import overlay
from translator.card_writer import name_objects, to_translator_card, write_card
from translator.events import find_events, timeline
from translator.execute import run_skill
from translator.meta import sam_track
from translator.perceive import Eyes
from translator.practice import ensure
from translator.robots import ROBOTS
from translator.scene import build, sample_layout


def learn(video, out, stage):
    """The card stage: Muse names the objects, SAM 3.1 tracks them and the hand, events, Muse writes the card.
    Writes the files into `out` and returns the runnable card, or None when no object moved."""
    t0 = time.time()
    names, _, cost = name_objects(video)
    (out / "names.json").write_text(json.dumps(names, indent=1))
    stage("Muse Spark names the objects", t0, cost, names=names)

    tracks = {}
    for role in ("moved_object", "container", "hand"):
        t0 = time.time()
        tracks[role] = sam_track(video, names[role])
        stage(f"SAM 3.1 tracks '{names[role]}'", t0, tracks[role]["cost_usd"], frames_with_match=len(tracks[role]["frames"]))
    (out / "tracks.json").write_text(json.dumps(
        [{**t, "frames": {str(f): {str(o): b for o, b in bx.items()} for f, bx in t["frames"].items()}} for t in tracks.values()]))
    overlay(video, list(tracks.values()), out / "tracks_overlay.mp4")

    import imageio.v2 as imageio
    meta = imageio.get_reader(video).get_meta_data()
    fps = meta.get("fps", 30)
    n_frames = int(round(meta.get("duration", 0) * fps))
    t0 = time.time()
    events = find_events(tracks["moved_object"], tracks["container"], tracks["hand"], fps, n_frames)
    (out / "events.json").write_text(json.dumps(events, indent=1))
    stage("events from the tracks", t0)
    print(timeline(events))
    if not events.get("moved_object"):
        return None

    t0 = time.time()
    card, _, cost = write_card(video, events, kind=names.get("kind", "pick_place"))
    (out / "card_muse.json").write_text(json.dumps(card, indent=1))
    runnable = to_translator_card(card)
    (out / "card.json").write_text(json.dumps(runnable, indent=1))
    stage("Muse Spark writes the skill card", t0, cost, card_name=card["name"], confidence=card["evidence"]["confidence"])
    return runnable


def check(robot, card, seed=0):
    """'can try', or why this robot cannot do the card: measured from its model, no tries."""
    scene = build(robot, card)
    if scene.refusal:
        return f"{scene.refusal[0].replace('_', ' ')}: {scene.refusal[1]}"
    try:
        sample_layout(scene, np.random.default_rng(seed))
    except (RuntimeError, ValueError) as e:
        return str(e) if str(e).startswith("no room") else f"no room: {e}"
    return "can try"


def try_robot(robot, card, out, trials=5, seed=0, stage=lambda *a, **k: None):
    """Practise the grip, then `trials` tries with the robot's cameras; the first try's clip goes to `out`.
    Returns 'ok/trials', or why the robot cannot do it."""
    t0 = time.time()
    scene = build(robot, card)
    if scene.refusal:
        label, why = scene.refusal
        stage(f"{robot}: cannot do it", t0, 0.0, why=why, kind="repeat")
        return f"{label.replace('_', ' ')}: {why}"
    try:
        practice = ensure(robot, card)
        scene = build(robot, card)
        sample_layout(scene, np.random.default_rng(seed))
    except (RuntimeError, ValueError) as e:
        stage(f"{robot}: cannot place the objects", t0, 0.0, why=str(e), kind="repeat")
        return f"no room: {e}"
    for old in out.glob(f"{robot}_trial0_*.mp4"):
        old.unlink()
    eyes = Eyes(scene)
    ok = 0
    for i in range(trials):
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed + i))
        scene.reset(cube, bowl, yaw)
        seen = eyes.find(card)
        if any(v is None for v in seen.values()):
            continue
        res = run_skill(scene, card, seen)
        ok += res.success
        if i == 0:
            save_video(scene, res.history, out / f"{robot}_trial0_{res.reason}.mp4")
    eyes.close()
    stage(f"{robot}: practise the grip, translate + check, {trials} trials", t0, 0.0, success=f"{ok}/{trials}",
          grip_depth_mm=round(practice["grip_depth"] * 1000), kind="repeat")
    return f"{ok}/{trials}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--robots", nargs="+", default=[n for n in ROBOTS if not n.endswith("_muse")],
                   help="default: every robot in the library")
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--robots-only", action="store_true", help="reuse this video's card from an earlier run, only redo the robots")
    p.add_argument("--check", action="store_true", help="only ask each robot if it can do the card, no tries")
    p.add_argument("--train", action="store_true", help="then train and test one policy per robot that passed")
    args = p.parse_args()
    video = Path(args.video)
    out = ROOT / "outputs" / "jobs" / video.stem
    out.mkdir(parents=True, exist_ok=True)
    report = {"video": str(video), "stages": []}

    def stage(name, t0, cost=None, **extra):
        report["stages"].append({"stage": name, "seconds": round(time.time() - t0, 1), "cost_usd": cost, **extra})
        print(f"[{name}] {time.time() - t0:.1f} s" + (f", ${cost:.4f}" if cost is not None else ""), flush=True)

    if args.robots_only:
        report = json.loads((out / "report.json").read_text())
        report["stages"] = [st for st in report["stages"] if st.get("kind") != "repeat"]
        runnable = json.loads((out / "card.json").read_text())
    else:
        runnable = learn(video, out, stage)
        (out / "report.json").write_text(json.dumps(report, indent=1))
        if runnable is None:
            sys.exit("no moved object found, stopping")
    learn_s = sum(s["seconds"] for s in report["stages"])
    report["robots"] = {}
    if args.check:
        for robot in args.robots:
            report["robots"][robot] = check(robot, runnable, args.seed)
            print(f"{robot:10s} {report['robots'][robot]}", flush=True)
        (out / "check.json").write_text(json.dumps(report["robots"], indent=1))
        return
    for robot in args.robots:
        report["robots"][robot] = try_robot(robot, runnable, out, args.trials, args.seed, stage)

    api = sum(s["cost_usd"] or 0 for s in report["stages"])
    report["summary"] = {"api_cost_usd": round(api, 4), "learn_seconds": round(learn_s, 1), "robots": report["robots"]}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"], indent=1))
    make_reel(job=out, cols=min(3, len(args.robots)))
    if args.train:
        if runnable.get("kind", "pick_place") != "pick_place":
            print(f"--train: datasets and policies are pick-and-place only so far, not '{runnable['kind']}'")
            return
        subprocess.run([sys.executable, str(ROOT / "scripts" / "train_job.py"), str(out)], check=True)


if __name__ == "__main__":
    main()
