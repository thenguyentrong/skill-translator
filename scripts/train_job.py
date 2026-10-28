"""A skill card -> for each robot: checked runs -> LeRobot dataset -> ACT policy -> test on new layouts.

  train_job.py cards/lemon_to_bowl.json --robots ur5e g1
  train_job.py outputs/jobs/lemon_into_bowl_1cycle            # a run_job folder: its card, the robots that passed
  train_job.py ... --episodes 200 --steps 40000 --trials 50

Datasets are made in parallel (CPU), policies train one at a time (GPU), each test runs while the next robot trains.
A step is skipped when its output is already there, so a stopped job picks up where it was.
Writes outputs/train_jobs/<card>/report.json, report.md and one log per step.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "bin" / "python"
ENV = {**os.environ, "MUJOCO_GL": "egl", "HF_HUB_OFFLINE": "1"}


def card_and_robots(source, robots):
    src = Path(source)
    if src.is_dir():
        card = src / "card.json"
        if not robots:
            done = json.loads((src / "report.json").read_text())["robots"]
            robots = [r for r, v in done.items() if re.match(r"[1-9]\d*/\d+$", str(v))]
        return card, robots
    if not robots:
        sys.exit("give --robots for a card file")
    return src, robots


def run(cmd, log):
    t0 = time.time()
    with open(log, "w") as f:
        code = subprocess.run([str(c) for c in cmd], cwd=ROOT, env=ENV, stdout=f, stderr=subprocess.STDOUT).returncode
    return code, round(time.time() - t0, 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="a card .json or a run_job output folder")
    p.add_argument("--robots", nargs="*")
    p.add_argument("--episodes", type=int, default=200)
    p.add_argument("--steps", type=int, default=40000)
    p.add_argument("--trials", type=int, default=50)
    p.add_argument("--parallel", type=int, default=3, help="datasets made at the same time")
    args = p.parse_args()
    card_path, robots = card_and_robots(args.source, args.robots)
    card = json.loads(card_path.read_text())
    name = card["name"]
    out = ROOT / "outputs" / "train_jobs" / name
    out.mkdir(parents=True, exist_ok=True)
    report = {"card": str(card_path.relative_to(ROOT) if card_path.is_relative_to(ROOT) else card_path),
              "episodes": args.episodes, "steps": args.steps, "trials": args.trials, "robots": {}}

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=1))
        rows = ["| Robot | Dataset | Training | Test on new layouts |", "|---|---|---|---|"]
        for r, v in report["robots"].items():
            ds, tr, ev = v.get("dataset", {}), v.get("train", {}), v.get("eval", {})
            rows.append(f"| {r} | {ds.get('episodes', '-')} of {ds.get('tries', '-')} tries, {ds.get('minutes', '-')} min | "
                        f"{tr.get('steps', '-')} steps, {tr.get('minutes', '-')} min | "
                        f"{ev.get('success', '-')}/{ev.get('trials', '-')} {ev.get('fails', '')} |")
        (out / "report.md").write_text(f"# {name}\n\n" + "\n".join(rows) + "\n")

    def dataset(robot):
        ds = ROOT / "outputs" / "datasets" / f"{robot}_{name}_{args.episodes}"
        gen = ds / "generation.json"
        secs = 0.0
        if not gen.exists():
            code, secs = run([PY, "scripts/make_dataset.py", robot, "--card", card_path, "--episodes", args.episodes,
                              "--out", ds, "--overwrite"], out / f"dataset_{robot}.log")
            if code or not gen.exists():
                return ds, {"error": f"make_dataset exit {code}, see dataset_{robot}.log"}
        s = json.loads(gen.read_text())["summary"]
        return ds, {"episodes": s["episodes_saved"], "tries": s["tries"], "minutes": round((secs or s["seconds_total"]) / 60, 1),
                    "path": str(ds.relative_to(ROOT))}

    def evaluate(robot, ckpt):
        code, secs = run([PY, "scripts/eval_policy.py", robot, "--card", card_path, "--policy", ckpt,
                          "--trials", args.trials, "--seed", 5000, "--videos", 1], out / f"eval_{robot}.log")
        res = ROOT / "outputs" / "eval" / f"{robot}_{name}_{args.steps:06d}.json"
        if code or not res.exists():
            return {"error": f"eval_policy exit {code}, see eval_{robot}.log"}
        s = json.loads(res.read_text())["summary"]
        fails = {k: v for k, v in s["fail_reasons"].items() if v}
        return {"success": s["success"], "trials": s["trials"], "fails": fails, "minutes": round(secs / 60, 1),
                "result": str(res.relative_to(ROOT))}

    t_start = time.time()
    with ThreadPoolExecutor(args.parallel) as datasets, ThreadPoolExecutor(1) as evals:
        made = {r: datasets.submit(dataset, r) for r in robots}
        tests = {}
        for robot in robots:
            ds, info = made[robot].result()
            report["robots"][robot] = {"dataset": info}
            save()
            if "error" in info or info["episodes"] < 10:
                print(f"{robot}: no dataset ({info})", flush=True)
                continue
            run_dir = ROOT / "outputs" / "train" / f"act_{robot}_{name}"
            ckpt = run_dir / "checkpoints" / f"{args.steps:06d}" / "pretrained_model"
            secs = 0.0
            if not ckpt.exists():
                if run_dir.exists():
                    sys.exit(f"{run_dir} exists without step {args.steps}; move it away or remove it first")
                code, secs = run([ROOT / ".venv" / "bin" / "lerobot-train", f"--dataset.repo_id=local/{robot}_{name}",
                                  f"--dataset.root={ds}", "--policy.type=act", "--policy.device=cuda",
                                  "--policy.push_to_hub=false", f"--output_dir={run_dir}", f"--job_name=act_{robot}_{name}",
                                  f"--steps={args.steps}", "--batch_size=8", f"--save_freq={min(10000, args.steps)}",
                                  "--log_freq=500", "--num_workers=8", "--wandb.enable=false"], out / f"train_{robot}.log")
                if code or not ckpt.exists():
                    report["robots"][robot]["train"] = {"error": f"lerobot-train exit {code}, see train_{robot}.log"}
                    save()
                    continue
            report["robots"][robot]["train"] = {"steps": args.steps, "minutes": round(secs / 60, 1),
                                                "checkpoint": str(ckpt.relative_to(ROOT))}
            save()
            print(f"{robot}: dataset {info['episodes']} episodes, trained {args.steps} steps", flush=True)
            tests[robot] = evals.submit(evaluate, robot, ckpt)
        for robot, f in tests.items():
            report["robots"][robot]["eval"] = f.result()
            save()
            print(f"{robot}: {report['robots'][robot]['eval']}", flush=True)
    report["minutes_total"] = round((time.time() - t_start) / 60, 1)
    save()
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
