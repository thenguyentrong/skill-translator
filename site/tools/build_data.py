"""Saved results -> site/public/data/site.json + small clips. Every number on the page comes from these files."""
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "public"
JOBS = ROOT / "outputs" / "jobs"
NAMES = {"so101": "SO-101", "panda": "Franka Panda", "ur5e": "UR5e", "g1": "Unitree G1", "xarm7": "xArm7", "lite6": "Lite6",
         "tienkung3": "TienKung 3", "oli": "LimX Oli", "fr3": "Franka FR3"}
ORDER = ["ur5e", "fr3", "panda", "xarm7", "lite6", "so101", "g1", "tienkung3", "oli"]
SAID_NO = {"too_big": "Too big for its gripper", "too_thin": "Handle too thin", "no_room": "No room in its reach", "two_hands": "Needs two hands",
           "must_walk": "Must walk, cannot", "too_heavy": "Too heavy", "two_hand_grip": "Two-hand grip not built", "handle_too_high": "Handle too high", "handle_too_low": "Handle too low"}
ROW = json.loads((ROOT / "outputs/matrix/matrix.json").read_text())


def plain(text, robot=None):
    t = re.sub(r"\b([a-z]+(?:_[a-z]+)+)\b", lambda m: m.group(1).replace("_", " "), str(text))
    t = re.sub(r"\(carry skills\)", "", t).strip()
    for k, v in NAMES.items():
        t = re.sub(rf"\bthe {k}\b", f"the {v}", t)
    return t[0].upper() + t[1:] if t else t


def clip(src, name, width=960, crf=26, speed=1.0):
    dst = OUT / "media" / name
    vf = f"scale='min({width},iw)':-2" + (f",setpts={1 / speed}*PTS" if speed != 1 else "")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-crf", str(crf), "-movflags", "+faststart", str(dst)], check=True)
    return f"media/{name}"


def cost(job):
    r = json.loads((JOBS / job / "report.json").read_text())
    learn = [s for s in r["stages"] if s["stage"].startswith(("Muse Spark", "SAM 3.1", "events"))]
    return {"seconds": round(sum(s["seconds"] for s in learn)), "usd": round(sum(s.get("cost_usd") or 0 for s in learn), 2)}


def matrix(skill):
    out = []
    by = {r["robot"]: r for r in ROW["rows"] if r["skill"] == skill}
    for rb in ORDER:
        r = by.get(rb)
        if not r:
            continue
        no = next((k for k, v in r["fails"].items() if v == r["n"] and k in SAID_NO), None)
        out.append({"robot": NAMES[rb], "no": SAID_NO[no] if no else None, "why": plain(fix(r.get("why", ""))) if no else None,
                    "score": None if no else f"{r['success']}/{r['n']}", "rate": 0 if no else r["success"] / r["n"]})
    return out


def fix(why):
    return "" if "341 mm" in str(why) else why  # known SO-101 measuring bug: show the verdict, not the wrong number


def answers(job):
    out = []
    check = json.loads((JOBS / job / "check.json").read_text())
    for rb in ORDER:
        if rb not in check:
            continue
        a = check[rb]
        if a == "can try":
            out.append({"robot": NAMES[rb], "no": None, "why": None})
        else:
            label, _, why = a.partition(":")
            key = label.strip().replace(" ", "_")
            out.append({"robot": NAMES[rb], "no": SAID_NO.get(key, plain(label)), "why": plain(fix(why.strip()))})
    return out


def card_words(job):
    c = json.loads((JOBS / job / "card.json").read_text())
    objs = []
    for k, o in c["objects"].items():
        size = o.get("size")
        bits = plain(k)
        if size:
            bits += " (" + " x ".join(f"{v * 100:.3g}" for v in size) + " cm)"
        elif "inner_radius" in o:
            bits += f" ({o['inner_radius'] * 200:.0f} cm across)"
        objs.append(bits)
    return {"kind": c.get("kind", "pick_place"), "goal": c["goal"], "objects": objs, "steps": [s["do"] for s in c["steps"]],
            "needs": c.get("needs", {})}


def policies():
    rows = []
    for rb, skill in [("g1", "cube_to_bowl"), ("ur5e", "lemon_to_bowl"), ("xarm7", "lemon_to_bowl"), ("tienkung3", "lemon_to_bowl"),
                      ("fr3", "lemon_to_bowl"), ("so101", "cube_to_bowl"), ("panda", "cube_to_bowl")]:
        s = json.loads((ROOT / f"outputs/eval/{rb}_{skill}_040000.json").read_text())["summary"]
        te = ROOT / f"outputs/eval/{rb}_{skill}_040000_te0.01.json"
        extra = json.loads(te.read_text())["summary"]["success"] if te.exists() else None
        rows.append({"robot": NAMES[rb], "skill": skill.replace("_to_", " to ").replace("_", " "), "ok": s["success"], "n": s["trials"], "smoothed": extra})
    return rows


def main():
    (OUT / "data").mkdir(exist_ok=True)
    (OUT / "media").mkdir(exist_ok=True)
    data = {"kinds": [
        {"id": "pick", "tab": "Pick and place", "title": "A hand puts a lemon into a bowl.", "credit": "Stock clip: \"Person Putting Orange in Bowl\" by SHVETS production, Pexels.", "job": cost("lemon_into_bowl_1cycle"), "overlay": clip(JOBS / "lemon_into_bowl_1cycle/tracks_overlay.mp4", "lemon_sam.mp4", 800, 27),
         "card": card_words("lemon_into_bowl_1cycle"), "result": clip(ROOT / "outputs/reel/lemon_to_bowl.mp4", "lemon_robots.mp4", 1100, 26), "robots": matrix("lemon_to_bowl"),
         "robots_title": "Each robot with this card, 10 tries with its own cameras"},
        {"id": "open", "tab": "Open a door", "title": "A woman opens a tall glass cabinet.", "credit": "Stock clip: \"Young Woman Taking Mug out of Cupboard\" by Ivan S, Pexels.", "job": cost("cabinet_door_open"), "overlay": clip(JOBS / "cabinet_door_open/tracks_overlay.mp4", "door_sam.mp4", 800, 27),
         "card": card_words("cabinet_door_open"), "answers": answers("cabinet_door_open"), "answers_title": "Every robot said no to this real cabinet: the door's swing is bigger than its reach.",
         "result": clip(ROOT / "outputs/reel/open_cabinet.mp4", "door_robots.mp4", 1100, 26), "robots": matrix("open_cabinet"), "robots_title": "A small tabletop cabinet instead (hand-written card), 10 tries each"},
        {"id": "carry", "tab": "Carry", "title": "A woman carries a large box through a gate.", "credit": "Stock clip: \"A Woman Taking Her Packages Inside\" by Kampus Production, Pexels.", "job": cost("basket_carry_walk"), "overlay": clip(JOBS / "basket_carry_walk/tracks_overlay.mp4", "carry_sam.mp4", 800, 27),
         "card": card_words("basket_carry_walk"), "answers": answers("basket_carry_walk"), "answers_title": "Every robot said no: too big, or no two-hand grip without handles yet.",
         "result": clip(ROOT / "outputs/reel/carry.mp4", "carry_robots.mp4", 1000, 26, 2.0), "robots": matrix("carry_crate"), "robots_title": "A crate with two handles (hand-written card), 10 tries each", "robots2": matrix("carry_basket"), "robots2_title": "A basket with a top handle (hand-written card), 10 tries each",
         "note": "Clip at double speed. Humanoids move between tables on a sliding base: the legs do not step."},
    ], "policies": policies()}
    R = set(SAID_NO)
    tried = [r for r in ROW["rows"] if not any(v == r["n"] and k in R for k, v in r["fails"].items())]
    data["matrix"] = {"ok": sum(r["success"] for r in tried), "n": sum(r["n"] for r in tried), "cells": len(tried), "skills": len(ROW["skills"]), "robots": len(ROW["robots"])}
    Image.open(ROOT / "outputs/reel/matrix.png").convert("RGB").resize((2000, 1257)).save(OUT / "media/matrix.webp", quality=80, method=6)
    clip(ROOT / "outputs/eval/g1_cube_to_bowl_040000_trial00_seed5000_ok.mp4", "policy_g1.mp4", 900, 26)
    data["policy_clip"] = "media/policy_g1.mp4"
    (OUT / "data/site.json").write_text(json.dumps(data, indent=1))
    print(json.dumps({k: v for k, v in data.items() if k != "kinds"})[:700])
    print([(k["id"], k["job"], k["card"]["goal"][:50], k["card"]["needs"]) for k in data["kinds"]])


main()
