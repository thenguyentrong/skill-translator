"""One step of a web job in its own process, so MuJoCo, EGL and the Meta API calls never block the server.

  python -m web.worker learn <video>                   # card stage -> outputs/jobs/<video stem>/
  python -m web.worker check <stem>                    # every robot: can try / why not -> check.json
  python -m web.worker try <stem> --robots a b --trials 5

Each step writes outputs/jobs/<stem>/web/<step>.json ({"state": running|done|failed, ...}); the server only reads files.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

JOBS = ROOT / "outputs" / "jobs"


def status(out, step, **fields):
    path = out / "web" / f"{step}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**old, **fields, "updated": time.time()}, indent=1))


def learn(video):
    from run_job import learn as learn_card
    out = JOBS / video.stem
    out.mkdir(parents=True, exist_ok=True)
    report = {"video": str(video.relative_to(ROOT)), "stages": []}

    def stage(name, t0, cost=None, **extra):
        report["stages"].append({"stage": name, "seconds": round(time.time() - t0, 1), "cost_usd": cost, **extra})
        (out / "report.json").write_text(json.dumps(report, indent=1))

    (out / "report.json").write_text(json.dumps(report, indent=1))
    for old in ("card.json", "card_muse.json", "check.json", "tracks_overlay.mp4"):
        (out / old).unlink(missing_ok=True)
    card = learn_card(video, out, stage)
    if card is None:
        raise RuntimeError("no object in the video moved more than 5 % of the frame width")
    return {"card": card["name"]}


def check(stem):
    from run_job import check as check_robot
    from translator.robots import ROBOTS
    out = JOBS / stem
    card = json.loads((out / "card.json").read_text())
    answers = {}
    for robot in ROBOTS:
        if robot.endswith("_muse"):
            continue
        answers[robot] = check_robot(robot, card)
        (out / "check.json").write_text(json.dumps(answers, indent=1))
    return {"robots": len(answers)}


def try_robots(stem, robots, trials):
    from run_job import try_robot
    out = JOBS / stem
    card = json.loads((out / "card.json").read_text())
    for robot in robots:
        status(out, f"run_{robot}", state="waiting", trials=trials)
    for robot in robots:
        status(out, f"run_{robot}", state="running", started=time.time())
        try:
            result = try_robot(robot, card, out, trials)
            clip = next(iter(sorted(out.glob(f"{robot}_trial0_*.mp4"))), None)
            status(out, f"run_{robot}", state="done", result=result, clip=clip.name if clip else None)
        except Exception as e:
            status(out, f"run_{robot}", state="failed", error=f"{type(e).__name__}: {e}"[:300])
    return {"robots": robots}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["learn", "check", "try"])
    p.add_argument("target", help="a video path (learn) or a job name")
    p.add_argument("--robots", nargs="*", default=[])
    p.add_argument("--trials", type=int, default=5)
    args = p.parse_args()
    target = Path(args.target).resolve() if args.step == "learn" else args.target
    out = JOBS / (target.stem if args.step == "learn" else target)
    out.mkdir(parents=True, exist_ok=True)
    status(out, args.step, state="running", started=time.time(), error=None)
    try:
        if args.step == "learn":
            result = learn(target)
        elif args.step == "check":
            result = check(target)
        else:
            result = try_robots(target, args.robots, args.trials)
        status(out, args.step, state="done", finished=time.time(), **result)
    except Exception as e:
        traceback.print_exc()
        status(out, args.step, state="failed", finished=time.time(), error=f"{type(e).__name__}: {e}"[:300])
        sys.exit(1)


if __name__ == "__main__":
    main()
