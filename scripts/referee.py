"""SAM referee: render clean robot clips, freeze a test set, and measure the referee against the simulator's own test.

  referee.py render [--trials 8]        clean clips (no labels) into outputs/referee/clips/, truth in truth.jsonl
  referee.py pick                       freeze the dev and test sets from those clips (sets.json); never redraws
  referee.py score dev|test             run the referee, then compare with the truth; writes report.md for test
  referee.py one <clip> --card <card>   one clip, no truth involved

The referee never opens truth.jsonl: only `score` does, after the verdicts are written.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from translator.referee import BUDGET, MAX_FRAMES, OUT, OverBudget, Spend, blind_question, referee

CLIPS = OUT / "clips"
TRUTH = OUT / "truth.jsonl"
SETS = OUT / "sets.json"
TRACKS = OUT / "tracks"
MUSE = OUT / "muse"
SIZE = (640, 480)
SEED = 7000  # not the matrix's seeds, not practice's

# Cells where a robot both passes and fails, across every container the pick-and-place cards use.
CELLS = [("ball_to_cup", "so101"), ("ball_to_cup", "panda"), ("lemon_to_bowl", "so101"), ("lemon_to_bowl", "oli"),
         ("can_to_bin", "panda"), ("can_to_bin", "so101"), ("cookie_to_plate", "panda"), ("potato_to_basket", "panda"),
         ("potato_to_basket", "ur5e"), ("kiwi_to_bowl", "g1"), ("kiwi_to_bowl", "so101"), ("block_to_plate", "g1"),
         ("block_to_plate", "oli"), ("cube_to_bowl", "oli")]
PER_CELL = 3


def load_card(name):
    return json.loads((ROOT / "cards" / f"{name}.json").read_text())


def clean_clip(scene, history, path, camera="front"):
    """No label on the picture, a fixed camera, at most MAX_FRAMES frames and always the last one."""
    import imageio.v2 as imageio
    import mujoco
    import numpy as np

    from translator.execute import FPS
    stride = max(1, math.ceil(len(history) / MAX_FRAMES))
    picked = list(range(len(history) - 1, -1, -stride))[::-1]
    d = mujoco.MjData(scene.model)
    with mujoco.Renderer(scene.model, SIZE[1], SIZE[0]) as r:
        frames = []
        for i in picked:
            d.qpos[:] = history[i]
            mujoco.mj_forward(scene.model, d)
            r.update_scene(d, camera=camera)
            frames.append(np.asarray(r.render()).copy())
    fps = FPS / stride
    imageio.mimsave(path, frames, fps=fps, codec="libx264", quality=7, macro_block_size=16,
                    output_params=["-movflags", "+faststart"])
    return fps, len(frames)


def render(args):
    import numpy as np

    from translator.execute import run_skill
    from translator.perceive import Eyes
    from translator.scene import build, sample_layout
    CLIPS.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)["clip"] for line in TRUTH.read_text().splitlines()} if TRUTH.exists() else set()
    for skill, robot in CELLS:
        card = load_card(skill)
        scene = build(robot, card)
        if scene.refusal:
            print(f"skip {skill} {robot}: {scene.refusal[0]}", flush=True)
            continue
        eyes = Eyes(scene)
        for i in range(args.trials):
            name = f"{skill}__{robot}__s{SEED + i}.mp4"
            if name in done:
                continue
            t0 = time.time()
            try:
                cube, bowl, yaw = sample_layout(scene, np.random.default_rng(SEED + i))
                scene.reset(cube, bowl, yaw)
                seen = eyes.find(card)
                if any(v is None for v in seen.values()):
                    print(f"{name}: unseen, no clip", flush=True)
                    continue
                res = run_skill(scene, card, seen)
                if not getattr(res, "history", None):
                    print(f"{name}: {res.reason}, no clip", flush=True)
                    continue
                fps, n = clean_clip(scene, res.history, CLIPS / name, args.camera)
            except Exception as e:
                print(f"{name}: error {e}"[:160], flush=True)
                continue
            c, b = scene.cube_pos(), scene.bowl_pos()
            row = {"clip": name, "skill": skill, "robot": robot, "seed": SEED + i, "fps": fps, "frames": n,
                   "sim_success": bool(res.success), "sim_reason": res.reason,
                   "sim_off_centre_m": round(float(np.linalg.norm(c[:2] - b[:2])), 4), "sim_height_m": round(float(c[2]), 4)}
            with TRUTH.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"{name}: {res.reason} {time.time() - t0:.1f}s", flush=True)
        eyes.close()
        del scene


def truth():
    return {r["clip"]: r for r in map(json.loads, TRUTH.read_text().splitlines())}


def pick(args):
    """Dev = one pass and one fail per container type, to fix prompts and thresholds. Test = 20 + 20 from the clips left,
    in seed order with a per-cell cap, every rim miss first. Nothing is left out for looking hard."""
    if SETS.exists():
        sys.exit(f"{SETS} already frozen; delete it by hand to redraw (and say so in the report)")
    rows = sorted(truth().values(), key=lambda r: (r["seed"], r["skill"], r["robot"]))
    used, dev = set(), []
    for skill in ("ball_to_cup", "lemon_to_bowl", "can_to_bin", "cookie_to_plate", "potato_to_basket"):
        for want in (True, False):
            r = next((r for r in rows if r["skill"] == skill and r["sim_success"] is want), None)
            if r:
                dev.append(r["clip"])
                used.add(r["clip"])
    test, count = {True: [], False: []}, {}
    rows.sort(key=lambda r: r["sim_reason"] != "bowl")  # stable: every rim miss goes in, they are the hardest failures
    for r in rows:
        key = (r["skill"], r["robot"], r["sim_success"])
        if r["clip"] in used or count.get(key, 0) >= PER_CELL or len(test[r["sim_success"]]) >= 20:
            continue
        count[key] = count.get(key, 0) + 1
        test[r["sim_success"]].append(r["clip"])
    SETS.write_text(json.dumps({"dev": dev, "test": test[True] + test[False]}, indent=1))
    print(f"dev {len(dev)}, test pass {len(test[True])} fail {len(test[False])}")


def _run_one(name, truth_row, spend):
    return referee(CLIPS / name, load_card(truth_row["skill"]), truth_row["fps"], TRACKS, spend, MUSE)


def score(args):
    sets = json.loads(SETS.read_text())
    t = truth()
    spend = Spend()
    rows = []
    for name in sets[args.which]:
        try:
            r = _run_one(name, t[name], spend)
        except OverBudget as e:
            print(f"STOP: {e}")
            break
        rows.append(r)
        print(f"{name}: {r['verdict']} ({r['decided_by']}: {r['why']})", flush=True)
    for r in rows:
        tr = t[r["clip"]]
        want = "pass" if tr["sim_success"] else "fail"
        r.update(sim=want, sim_reason=tr["sim_reason"], skill=tr["skill"], robot=tr["robot"],
                 sim_off_centre_m=tr["sim_off_centre_m"], agree=r["verdict"] == want)
    (OUT / f"results_{args.which}.json").write_text(json.dumps(rows, indent=1, default=str))
    summary = summarise(rows, spend)
    print(json.dumps(summary, indent=1))
    if args.which == "test":
        write_report(rows, summary)


def summarise(rows, spend):
    n = len(rows)
    sam = [r for r in rows if r["decided_by"] == "sam"]
    muse = [r for r in rows if r["decided_by"] == "muse"]
    never = [r for r in rows if r["why"] == "object never moved"]
    moved = [r for r in rows if r["sim"] == "fail" and r["why"] != "object never moved"]
    secs = sorted(r["seconds"] for r in rows)
    return {
        "clips": n, "agree": sum(r["agree"] for r in rows), "agreement_pct": round(100 * sum(r["agree"] for r in rows) / max(n, 1), 1),
        "sim_pass_clips": sum(r["sim"] == "pass" for r in rows), "sim_fail_clips": sum(r["sim"] == "fail" for r in rows),
        "false_pass": sum(r["sim"] == "fail" and r["verdict"] == "pass" for r in rows),
        "false_fail": sum(r["sim"] == "pass" and r["verdict"] == "fail" for r in rows),
        "unsure": sum(r["verdict"] == "unsure" for r in rows),
        "sam_decided": len(sam), "sam_agree": sum(r["agree"] for r in sam),
        "muse_decided": len(muse), "muse_agree": sum(r["agree"] for r in muse),
        "seconds_per_clip_median": secs[n // 2] if n else None, "seconds_per_clip_max": secs[-1] if n else None,
        "cost_this_set_usd": round(sum(r["cost_usd"] for r in rows), 3), "cost_per_clip_usd": round(sum(r["cost_usd"] for r in rows) / max(n, 1), 4),
        "all_api_spend_usd": round(spend.total, 3),
        "interval_95_pct": wilson(sum(r["agree"] for r in rows), n),
        "plain_box_test_agree": sum(bool((r.get("events") or {}).get("ends_inside_container")) == (r["sim"] == "pass") for r in rows),
        "never_moved": len(never), "never_moved_right": sum(r["agree"] for r in never),
        "moved_fails": len(moved), "moved_fails_right": sum(r["agree"] for r in moved),
    }


def wilson(k, n, z=1.96):
    """95 % interval for k right out of n; a small set cannot claim a sharp number."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (mid - half), 1), round(100 * (mid + half), 1)]


def write_report(rows, s):
    by_reason = {}
    for r in rows:
        a = by_reason.setdefault(r["sim_reason"], [0, 0])
        a[0] += r["agree"]
        a[1] += 1
    wrong = [r for r in rows if not r["agree"]]
    low, high = s["interval_95_pct"]
    plural = "" if s["muse_decided"] == 1 else "s"
    lines = [
        "# SAM referee: measured agreement", "",
        f"**{s['agree']} of {s['clips']} clips agree with the simulator's own success test ({s['agreement_pct']} %).** "
        f"With only {s['clips']} clips the 95 % interval is {low} to {high} %.", "",
        f"- False pass (said done, was not): {s['false_pass']}. False fail: {s['false_fail']}. Unsure: {s['unsure']}.",
        f"- SAM alone decided {s['sam_decided']} clips, {s['sam_agree']} right. Muse broke {s['muse_decided']} tie{plural} blind, "
        f"{s['muse_agree']} right.",
        f"- Cost ${s['cost_this_set_usd']} for this set, ${s['cost_per_clip_usd']:.3f} per clip. Median {s['seconds_per_clip_median']:.1f} s "
        f"per clip, slowest {s['seconds_per_clip_max']:.1f} s.",
        f"- Plain box test from events.py, no margin and no Muse: {s['plain_box_test_agree']} of {s['clips']}.",
        f"- Easy part: in {s['never_moved']} failed clips the object never moved, all {s['never_moved_right']} right. "
        f"Harder part: {s['moved_fails']} failed clips where it moved, {s['moved_fails_right']} right.", "",
        "## What this does and does not show", "",
        f"{s['sim_pass_clips']} clips the simulator passed and {s['sim_fail_clips']} it failed, clean renders with no labels, at most "
        f"{MAX_FRAMES} frames, one fixed camera, seeds from {SEED}. Pick-and-place cards only; door and carry cards are not covered. "
        "The scene paints the object red and the container green, and the camera never moves, so this is the easy case for "
        "vision. It says nothing yet about real phone video.", "",
        "One prompt changed on the dev set before the test: a flat cylinder is a \"red disc\", because \"red cylinder\" found no "
        f"cookie. Thresholds stayed as first written. The test ran once and the rules did not change after it. Dev set: 10 of 10, "
        "3 of 3 ties right.", "",
        "| How the simulator scored it | Right | Clips |", "|---|---|---|",
    ]
    lines += [f"| {k} | {a} | {b} |" for k, (a, b) in sorted(by_reason.items())]
    lines += ["", "## Wrong cases", ""]
    if not wrong:
        lines.append("None.")
    else:
        lines += ["| Clip | Simulator | Referee | Decided by | Why | Off-centre (m) |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['clip']} | {r['sim']} ({r['sim_reason']}) | {r['verdict']} | {r['decided_by']} | {r['why']} | "
                  f"{r['sim_off_centre_m']} |" for r in wrong]
    lines += ["", "## What Muse is told", "", "Clip plus this question, with the card's shapes filled in. Never the pixels' score:", "",
              "> " + blind_question(load_card("ball_to_cup")), ""]
    text = "\n".join(lines)
    (OUT / "report.md").write_text(text)
    (ROOT / "docs" / "referee.md").write_text(text)
    print(f"wrote {OUT / 'report.md'} and docs/referee.md")


def one(args):
    fps = float(Fraction(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=r_frame_rate",
                                                  "-of", "csv=p=0", args.clip], text=True).strip().split(",")[0]))
    r = referee(args.clip, json.loads(Path(args.card).read_text()), fps, TRACKS, Spend(), MUSE)
    print(json.dumps({k: r.get(k) for k in ("verdict", "decided_by", "why", "end_distance", "seconds", "cost_usd")}, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("render")
    a.add_argument("--trials", type=int, default=8)
    a.add_argument("--camera", default="front")
    a.set_defaults(fn=render)
    sub.add_parser("pick").set_defaults(fn=pick)
    a = sub.add_parser("score")
    a.add_argument("which", choices=["dev", "test"])
    a.set_defaults(fn=score)
    a = sub.add_parser("one")
    a.add_argument("clip")
    a.add_argument("--card", required=True)
    a.set_defaults(fn=one)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
