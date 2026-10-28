"""A skill gets better in a loop: every robot runs the card, Muse Spark checks the runs against the human video and
improves the card, and the new card is kept only if more tries pass on the same layouts.

  review_job.py outputs/jobs/cookie_into_plate [--rounds 2] [--trials 10] [--robots so101 g1 ...] [--judge 6]
Writes <job>/review/round<k>/ (card.json, clips) and <job>/review/review.json with every check, change and score;
the best card goes to <job>/card_reviewed.json.
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
sys.path.insert(0, str(ROOT / "scripts"))

import matrix
from translator import review
from translator.practice import ensure
from translator.robots import ROBOTS

SEED = 0


def run_round(card, robots, trials, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / "card.json").write_text(json.dumps(card, indent=1))
    for r in robots:
        ensure(r, card)
    matrix.OUT = out  # the forked workers write their clips here
    with Pool(min(12, len(robots))) as pool:
        rows = list(pool.imap_unordered(matrix.cell, [(card["name"], card, r, trials, SEED, "fail") for r in robots]))
    return sorted(rows, key=lambda r: robots.index(r["robot"]))


def refused(row):
    return any(v == row["n"] and k in matrix.REFUSALS for k, v in row["fails"].items())


def score(rows):
    return sum(r["success"] for r in rows if not refused(r))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("job", help="a run_job output folder (its card.json and video)")
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--trials", type=int, default=10)
    p.add_argument("--robots", nargs="*", default=[n for n in ROBOTS if not n.endswith("_muse")])
    p.add_argument("--judge", type=int, default=6, help="robots Muse checks per round (most failures first)")
    args = p.parse_args()
    job = Path(args.job)
    video = ROOT / json.loads((job / "report.json").read_text())["video"]
    base = json.loads((job / "card.json").read_text())
    out = job / "review"
    log = {"video": str(video.relative_to(ROOT)), "rounds": []}
    cost = 0.0

    card, name = base, base["name"]
    rows = run_round(card, args.robots, args.trials, out / "round0")
    best = {"card": card, "rows": rows, "score": score(rows), "round": 0}
    log["round0"] = {"rows": rows, "score": best["score"]}
    print(f"round 0: {best['score']} passed  " + ", ".join(f"{r['robot']} {r['success']}/{r['n']}" for r in rows), flush=True)
    for k in range(1, args.rounds + 1):
        t0 = time.time()
        failing = sorted([r for r in best["rows"] if not refused(r) and r["success"] < r["n"]], key=lambda r: r["success"])
        judgments = {}
        folder = out / f"round{best['round']}"
        for r in failing[:args.judge]:
            clip = folder / f"{best['card']['name']}__{r['robot']}_fail.mp4"
            clip = clip if clip.exists() else folder / f"{best['card']['name']}__{r['robot']}.mp4"
            verdict, c = review.judge(video, clip, best["card"], r["robot"], {**r, "clip_failed": "_fail" in clip.name})
            judgments[r["robot"]] = verdict
            cost += c or 0
            print(f"  check {r['robot']}: {verdict['fix_in']} / {verdict['cause']}: {verdict['what_happened']}", flush=True)
        tried = [r for r in log["rounds"] if r.get("kept") is False and r["from_round"] == best["round"]]
        plan, c = review.improve(video, best["card"], best["rows"], judgments, tried)
        cost += c or 0
        entry = {"round": k, "from_round": best["round"], "judgments": judgments, "changes": plan["changes"],
                 "summary": plan["summary"], "llm_seconds": round(time.time() - t0, 1)}
        print(f"  Muse: {plan['summary']}", flush=True)
        if not plan["changes"]:
            entry["result"] = "no changes proposed"
            log["rounds"].append(entry)
            break
        card, skipped = review.apply(best["card"], plan["changes"])
        card["name"] = f"{name}_r{k}"
        rows = run_round(card, args.robots, args.trials, out / f"round{k}")
        new = score(rows)
        worse = [r["robot"] for r, o in zip(rows, best["rows"]) if r["success"] < o["success"] - 1]
        kept = new > best["score"] and not worse
        entry.update(skipped=skipped, rows=rows, score=new, before=best["score"], kept=kept, worse=worse)
        log["rounds"].append(entry)
        print(f"round {k}: {new} passed (before {best['score']}){' - kept' if kept else ' - not kept'}"
              f"{f', worse on {worse}' if worse else ''}  " + ", ".join(f"{r['robot']} {r['success']}/{r['n']}" for r in rows), flush=True)
        if kept:
            best = {"card": card, "rows": rows, "score": new, "round": k}
    log.update(best_round=best["round"], best_score=best["score"], api_cost_usd=round(cost, 4))
    (out / "review.json").write_text(json.dumps(log, indent=1))
    (job / "card_reviewed.json").write_text(json.dumps({**best["card"], "name": name}, indent=1))
    print(f"best: round {best['round']}, {best['score']} passed; Muse cost ${cost:.3f}")


if __name__ == "__main__":
    main()
