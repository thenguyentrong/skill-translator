"""A robot the code has never seen: Muse reads its model file and writes the adapter, then fixes it from measurements,
test results and replay frames (at most 3 fixes). An adapter that passes goes into robots/muse/<name>.json.

  write_adapter.py mujoco_menagerie/ufactory_xarm7/xarm7.xml --name xarm7
  write_adapter.py mujoco_menagerie/universal_robots_ur5e/ur5e.xml --name ur5e_muse --fix-model baseten
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mujoco
import numpy as np

from translator import robots
from translator.adapter_writer import ask, feedback_message, first_message, to_adapter
from translator.blueprint import facts, measure
from translator.execute import run_skill
from translator.perceive import Eyes
from translator.practice import practice
from translator.scene import build, practice_file, sample_layout
from translator.translate import load_card

CARDS = [load_card(ROOT / "cards" / f"{c}.json") for c in ("cube_to_bowl", "block_to_plate")]
OUT = ROOT / "outputs" / "adapters"


def test(adapter, n, seed=0):
    """Per card: practise the grip, then n trials with camera vision. Returns (results, frames of the first failure)."""
    robot = robots.from_dict(adapter)
    robots.ROBOTS[robot.name] = robot
    results, frames, ok = {}, [], 0
    for card in CARDS:
        practice_file(robot.name, card).unlink(missing_ok=True)
        try:
            pr = practice(robot.name, card, n=6)
            scene = build(robot.name, card)
            sample_layout(scene, np.random.default_rng(seed))
        except Exception as e:
            results[card["name"]] = {"success": f"0/{n}", "error": f"{type(e).__name__}: {e}"[:600]}
            continue
        eyes = Eyes(scene)
        rows = []
        for i in range(n):
            cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed + i))
            scene.reset(cube, bowl, yaw)
            seen = eyes.find(card)
            if any(v is None for v in seen.values()):
                rows.append({"trial": i, "result": "objects not seen"})
                continue
            labels = []
            try:
                res = run_skill(scene, card, seen, on_tick=labels.append)
            except Exception as e:
                rows.append({"trial": i, "result": f"error {type(e).__name__}: {e}"[:200]})
                continue
            if res.reason == "too_big":
                rows.append({"trial": i, "result": "too_big: " + res.cube_at["why"]})
                continue
            rows.append({"trial": i, "result": res.reason,
                         "ik_error_mm": {k: round(v * 1000, 1) for k, v in res.pos_err.items()},
                         "object_height_after_lift_mm": round((res.cube_at["lift"][2] - 0.75) * 1000, 1)})
            if not res.success and not frames:
                frames = _frames(scene, res.history, labels)
        eyes.close()
        k = sum(r["result"] == "ok" for r in rows)
        ok += k
        results[card["name"]] = {"success": f"{k}/{n}", "trials": rows,
                                 "practice": {"grip_depth_mm": round(pr["grip_depth"] * 1000), "tries": pr["tries"]}}
    results["meaning of results"] = {"ik": "the arm could not reach a waypoint (>1 cm off)", "grasp": "object not lifted",
                                     "drop": "object lifted but lost before the container",
                                     "bowl": "carried to the container but not inside"}
    return {"success": f"{ok}/{n * len(CARDS)}", "ok": ok, **results}, frames


def _frames(scene, history, labels, size=(480, 360)):
    ends = [max(i for i, l in enumerate(labels) if l == step) + 1 for step in ("descend", "close", "lift") if step in labels]
    m = scene.model
    d = mujoco.MjData(m)
    out = []
    with mujoco.Renderer(m, size[1], size[0]) as r:
        for i in ends:
            d.qpos[:] = history[min(i, len(history) - 1)]
            mujoco.mj_forward(m, d)
            r.update_scene(d, camera="front")
            out.append(r.render())
    return out


def model_text(xml, seen=None):
    """The model file with the files it includes appended, so Muse sees the whole robot."""
    seen = seen or set()
    seen.add(xml)
    text = xml.read_text()
    for inc in re.findall(r'<include\s+file="([^"]+)"', text):
        f = (xml.parent / inc).resolve()
        if f.exists() and f not in seen:
            text += f"\n\n<!-- included file {inc} -->\n" + model_text(f, seen)
    return text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("xml", help="model file, relative to assets/robots/")
    p.add_argument("--name", required=True)
    p.add_argument("--model", choices=["meta", "baseten", "fireworks"], default="meta", help="who writes the first adapter")
    p.add_argument("--fix-model", choices=["meta", "baseten", "fireworks"], default="meta", help="who fixes it")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--trials", type=int, default=5, help="per card")
    p.add_argument("--pass", dest="need", type=int, default=8, help="successes needed over both cards")
    args = p.parse_args()
    xml = robots.ASSETS / args.xml
    out = OUT / args.name
    out.mkdir(parents=True, exist_ok=True)
    f = facts(xml)
    messages = [("user", first_message(model_text(xml), f))]
    report = {"robot": args.name, "xml": args.xml, "rounds": []}

    model = args.model
    for rnd in range(args.rounds + 1):
        t0 = time.time()
        answer, cost, secs = ask(messages, model=model, images=images if rnd else ())
        adapter = to_adapter(answer, args.xml)
        adapter["name"] = args.name
        (out / f"round{rnd}.json").write_text(json.dumps(adapter, indent=1))
        measurements, _ = measure(adapter)
        if measurements.get("loads"):
            results, images = test(adapter, args.trials)
            if measurements.get("robot_parts_touching_table_at_home"):
                results["ok"] = 0
                results["success"] = f"0/{args.trials * len(CARDS)} (not counted: the robot cuts into the table)"
                results["problem"] = ("these robot parts touch or cut into the table at the home pose: "
                                      f"{measurements['robot_parts_touching_table_at_home']}; move the base back or "
                                      "change the home pose")
        else:
            results, images = {"success": f"0/{args.trials * len(CARDS)}", "ok": 0, "error": "the model did not load"}, []
        row = {"round": rnd, "model": model, "llm_seconds": secs, "cost_usd": cost, "success": results["success"],
               "test_seconds": round(time.time() - t0 - secs, 1), "measurements": measurements,
               "results": results, "adapter": adapter}
        report["rounds"].append(row)
        (out / "report.json").write_text(json.dumps(report, indent=1))
        print(f"round {rnd} ({model}, {secs} s, ${cost or 0:.4f}): {results['success']}  "
              f"axes {adapter['approach_axis']}/{adapter['closing_axis']} gripper {adapter['gripper']} "
              f"{adapter['gripper_open']}->{adapter['gripper_closed']} yaw {adapter['base_yaw']:.2f}", flush=True)
        if results["ok"] >= args.need:
            break
        messages += [("assistant", json.dumps(answer)), ("user", feedback_message(adapter, measurements, results))]
        model = args.fix_model

    best = max(report["rounds"], key=lambda r: (r["results"]["ok"], -r["round"]))
    report["final"] = {"round": best["round"], "fix_rounds": best["round"], "success": best["success"],
                       "api_cost_usd": round(sum(r["cost_usd"] or 0 for r in report["rounds"]), 4)}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    (out / "best.json").write_text(json.dumps(best["adapter"], indent=1))
    if best["results"]["ok"] < args.need:
        print(json.dumps(report["final"]), "-> not good enough, not added to the library;", (out / "best.json").relative_to(ROOT))
        return
    dest = robots.ADAPTERS / "muse" / f"{args.name}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(best["adapter"], indent=1))
    print(json.dumps(report["final"]), "->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
