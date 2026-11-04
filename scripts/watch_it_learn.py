"""Watch it learn: one layout at each saved checkpoint in a 1920x1080 grid, labelled with steps and the real score.

Reads the eval_policy.py results in --evals (one JSON per checkpoint, same seeds, no video) and --evals/clips (one
recorded trial per checkpoint, same seed) and writes --out .mp4 + .json. The clip layout comes from a fixed rule,
written into the JSON; the score is always all layouts. Without --seed it only prints the seed to record.
"""
import argparse
import json
import math
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 960, 540
BAR = 58
FPS = 25
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PLAIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
GOOD, BAD, INK = (86, 214, 134), (255, 120, 110), (245, 245, 245)
WORDS = {"not_lifted": "never lifted it", "dropped": "dropped it", "near_bowl_outside": "missed the bowl"}


def wilson(k, n, z=1.96):
    """95 % range of the true success rate given k of n."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - r), 3), round(min(1.0, c + r), 3)]


def pick_seed(steps, by_seed):
    """Lowest seed that goes fail -> ok once and stays ok; else lowest seed failing first and ok last; else the first."""
    seeds = sorted(by_seed[steps[0]])
    ok = lambda s: [by_seed[st][s]["success"] for st in steps]
    for s in seeds:
        o = ok(s)
        if not o[0] and o[-1] and o == sorted(o):
            return s, "lowest seed that fails at the first checkpoint, then works at every later one"
    for s in seeds:
        o = ok(s)
        if not o[0] and o[-1]:
            return s, "lowest seed that fails at the first checkpoint and works at the last one (not monotonic)"
    return seeds[0], "no seed went from fail to ok, so the first seed"


def label(step, rows, row):
    bar = Image.new("RGB", (W, BAR), (18, 20, 24))
    d = ImageDraw.Draw(bar)
    k, n = sum(r["success"] for r in rows), len(rows)
    d.text((16, 11), f"{step:,} steps", font=ImageFont.truetype(BOLD, 28), fill=INK)
    d.text((274, 11), f"{k}/{n} layouts", font=ImageFont.truetype(BOLD, 28), fill=INK)
    if row["success"]:
        text, colour = f"this one: in bowl at {row['time_to_success_s']:.1f} s", GOOD
    else:
        text, colour = f"this one: {WORDS[row['reason']]}", BAD
    font = ImageFont.truetype(PLAIN, 22)
    d.text((W - 16 - d.textlength(text, font=font), 15), text, font=font, fill=colour)
    return np.asarray(bar)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--evals", default="outputs/eval/watch_it_learn")
    p.add_argument("--out", default="outputs/preview/watch_it_learn")
    p.add_argument("--seed", type=int, default=None, help="clip layout (the fixed rule in pick_seed names it)")
    args = p.parse_args()

    evals = ROOT / args.evals
    runs = sorted(evals.glob("*.json"), key=lambda f: int(json.loads(f.read_text())["summary"]["checkpoint_step"]))
    if len(runs) != 4:
        raise SystemExit(f"need 4 eval JSONs in {evals}, found {len(runs)}")
    data = [json.loads(f.read_text()) for f in runs]
    steps = [int(d["summary"]["checkpoint_step"]) for d in data]
    seed_lists = {tuple(r["seed"] for r in d["trials"]) for d in data}
    if len(seed_lists) != 1:
        raise SystemExit("the checkpoints were not run on the same layouts")
    by_seed = {st: {r["seed"]: r for r in d["trials"]} for st, d in zip(steps, data)}
    seed, why = pick_seed(steps, by_seed)
    if args.seed is None:
        raise SystemExit(f"record seed {seed} ({why}), then pass --seed {seed}")
    if args.seed != seed:
        seed, why = args.seed, "chosen by hand with --seed"

    clips = {}
    for f in (evals / "clips").glob("*.json"):
        d = json.loads(f.read_text())
        if d["trials"][0]["seed"] == seed:
            clips[int(d["summary"]["checkpoint_step"])] = d["trials"][0]
    if sorted(clips) != steps:
        raise SystemExit(f"need a clip of seed {seed} for {steps}, found {sorted(clips)}")

    readers, bars, lengths = [], [], []
    for st, d in zip(steps, data):
        row = clips[st]
        path = ROOT / row["video"]
        readers.append(imageio.get_reader(path))
        lengths.append(readers[-1].count_frames())
        bars.append(label(st, d["trials"], row))

    if len(set(lengths)) != 1:
        raise SystemExit(f"clips differ in length: {lengths}")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(out.with_suffix(".mp4"), fps=FPS, codec="libx264", quality=8, macro_block_size=8,
                                pixelformat="yuv420p", ffmpeg_params=["-movflags", "+faststart"])
    for group in zip(*readers):
        cells = []
        for i, f in enumerate(group):
            img = np.asarray(Image.fromarray(f).resize((W, H), Image.LANCZOS)).copy()
            img[:BAR] = bars[i]
            cells.append(img)
        last = cells
        writer.append_data(np.vstack([np.hstack(cells[:2]), np.hstack(cells[2:])]))
    for _ in range(FPS * 2):  # hold the end so the result can be read
        writer.append_data(np.vstack([np.hstack(last[:2]), np.hstack(last[2:])]))
    writer.close()

    scores = [sum(r["success"] for r in d["trials"]) for d in data]
    checkpoints = []
    for st, d, k in zip(steps, data, scores):
        s = d["summary"]
        checkpoints.append({"step": st, "success": k, "trials": s["trials"], "success_rate": s["success_rate"],
                            "rate_95_percent_range": wilson(k, s["trials"]), "fail_reasons": s["fail_reasons"],
                            "mean_time_to_success_s": s["mean_time_to_success_s"], "eval_json": str(runs[steps.index(st)].relative_to(ROOT)),
                            "clip": clips[st]["video"], "clip_result": clips[st]["reason"],
                            "clip_matches_scored_trial": clips[st]["reason"] == by_seed[st][seed]["reason"]})
    per_seed = {str(s): {str(st): by_seed[st][s]["reason"] for st in steps} for s in sorted(by_seed[steps[0]])}
    pairs = list(zip(scores, scores[1:]))
    result = {
        "robot": data[0]["summary"]["robot"], "card": data[0]["summary"]["card"], "policy": "ACT, 200 episodes",
        "first_seed": data[0]["summary"]["first_seed"], "trials_per_checkpoint": data[0]["summary"]["trials"],
        "settings": {"n_action_steps": data[0]["summary"]["n_action_steps"],
                     "temporal_ensemble_coeff": data[0]["summary"]["temporal_ensemble_coeff"]},
        "scores": dict(zip(map(str, steps), scores)), "improves_at_every_step": all(b > a for a, b in pairs),
        "never_gets_worse": all(b >= a for a, b in pairs), "checkpoints": checkpoints,
        "clip": {"seed": seed, "rule": why}, "layouts": per_seed,
        "layouts_lost_from_first_to_last": [s for s, r in per_seed.items() if r[str(steps[0])] == "ok" and r[str(steps[-1])] != "ok"],
        "layouts_won_from_first_to_last": [s for s, r in per_seed.items() if r[str(steps[0])] != "ok" and r[str(steps[-1])] == "ok"],
    }
    out.with_suffix(".json").write_text(json.dumps(result, indent=1))
    print(f"scores {result['scores']}, clip seed {seed} ({why})")
    print(f"saved {out.with_suffix('.mp4')} and .json")


if __name__ == "__main__":
    main()
