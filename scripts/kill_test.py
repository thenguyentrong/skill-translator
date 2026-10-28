"""Kill test: the hand-written skill card on random cube/bowl poses, N trials per robot."""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import imageio.v2 as imageio
import mujoco
import numpy as np

from translator.execute import CONTACT_STEPS, FPS, run_skill
from translator.perceive import Eyes
from translator.practice import ensure
from translator.render import Cameras
from translator.scene import build, sample_layout
from translator.translate import load_card

OUT = ROOT / "outputs" / "kill_test"


def save_video(scene, history, path, size=(720, 540)):
    """Main view on the left, the robot's own cameras (front, top, wrist) stacked on the right."""
    m = scene.model
    d = mujoco.MjData(m)
    cam = scene.camera()
    cams = Cameras(m, size[0] // 3, size[1] // 3)
    with mujoco.Renderer(m, size[1], size[0]) as r:
        frames = []
        for q in history:
            d.qpos[:] = q
            mujoco.mj_forward(m, d)
            r.update_scene(d, camera=cam)
            frames.append(np.concatenate([r.render(), cams.column(d)], axis=1))
    cams.close()
    imageio.mimsave(path, frames, fps=FPS, codec="libx264", quality=7, macro_block_size=4,
                    ffmpeg_params=["-movflags", "+faststart"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("robots", nargs="*", default=["so101", "panda"])
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--card", default=str(ROOT / "cards" / "cube_to_bowl.json"))
    p.add_argument("--videos", choices=["none", "fail", "first+fail", "all"], default="first+fail")
    p.add_argument("--eyes", choices=["camera", "sim"], default="camera",
                   help="camera: the robot finds the objects in its own images; sim: it is told the true poses")
    p.add_argument("--no-practice", action="store_true", help="skip the grip practice (grip depth 0 unless saved)")
    args = p.parse_args()
    card = load_card(args.card)

    summary = {}
    for name in args.robots:
        if not args.no_practice:
            pr = ensure(name, card)
            print(f"{name}: practice grip depth {pr['grip_depth'] * 1000:+.0f} mm ({pr['success']}/{pr['n']}), tries {pr['tries']}", flush=True)
        scene = build(name, card)
        eyes = Eyes(scene) if args.eyes == "camera" else None
        out = OUT / name
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(args.n):
            seed = args.seed + i
            cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
            scene.reset(cube, bowl, yaw)
            t0 = time.time()
            true = scene.true_objects()
            seen = eyes.find(card) if eyes else true
            if any(v is None for v in seen.values()):
                rows.append({"seed": seed, "success": False, "reason": "unseen"})
                print(f"{name:6s} seed {seed:3d}: FAIL unseen", flush=True)
                continue
            res = run_skill(scene, card, seen)
            if res.reason == "too_big":
                rows.append({"seed": seed, "success": False, "reason": "too_big", "why": res.cube_at["why"]})
                print(f"{name:6s} seed {seed:3d}: FAIL too_big ({res.cube_at['why']})", flush=True)
                continue
            row = {
                "seed": seed, "success": res.success, "reason": res.reason,
                "eyes_err_mm": {k: round(float(np.linalg.norm(seen[k]["pos"][:2] - true[k]["pos"][:2])) * 1000, 1) for k in seen},
                "cube": np.round(cube, 3).tolist(), "bowl": np.round(bowl, 3).tolist(), "yaw_deg": round(math.degrees(yaw), 1),
                "ik_pos_err_mm": {k: round(v * 1000, 1) for k, v in res.pos_err.items()},
                "ik_rot_err_deg": {k: round(math.degrees(v), 1) for k, v in res.rot_err.items()},
                "cube_z_after_lift_mm": round((res.cube_at["lift"][2] - 0.75) * 1000, 1),
                "final_cube": np.round(scene.cube_pos(), 3).tolist(),
            }
            rows.append(row)
            want = args.videos == "all" or (not res.success and args.videos != "none") or (i == 0 and args.videos == "first+fail")
            if want:
                save_video(scene, res.history, out / f"seed{seed:03d}_{res.reason}.mp4")
            print(f"{name:6s} seed {seed:3d}: {'OK  ' if res.success else 'FAIL'} {res.reason:5s} "
                  f"ik err grasp/release {max(res.pos_err[k] for k in CONTACT_STEPS) * 1000:4.1f} mm, "
                  f"free space {max(res.pos_err.values()) * 1000:4.1f} mm / {math.degrees(max(res.rot_err.values())):4.1f} deg, "
                  f"cube z after lift {row['cube_z_after_lift_mm']:6.1f} mm, eyes err {row['eyes_err_mm']}  ({time.time() - t0:.1f} s)", flush=True)
        ok = sum(r["success"] for r in rows)
        reasons = {}
        for r in rows:
            if not r["success"]:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        summary[name] = {"success": ok, "n": args.n, "fail_reasons": reasons}
        if eyes:
            eyes.close()
        (out / f"results_{args.eyes}_seed{args.seed}_n{args.n}.json").write_text(json.dumps({"summary": summary[name], "trials": rows}, indent=1))
    print()
    for name, s in summary.items():
        print(f"{name:6s} {s['success']}/{s['n']}  fails: {s['fail_reasons'] or '-'}")


if __name__ == "__main__":
    main()
