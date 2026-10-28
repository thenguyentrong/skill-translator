"""Run a trained LeRobot policy (e.g. ACT) closed-loop in the simulation and report its success rate.

Each trial: random layout (seed) -> every 1/25 s the policy sees exactly what make_dataset.py recorded (arm joint
angles + gripper closure, front/top/wrist images) and sends arm joint targets + a 0..1 grip command -> after the time
limit the arm holds still for 1 s -> the card's success test (cube inside the bowl).
"""
import argparse
import json
import math
import os
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore", message="Cannot enable progress bars")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import imageio.v2 as imageio
import mujoco
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
from lerobot.policies import get_policy_class, make_pre_post_processors
from lerobot.policies.utils import prepare_observation_for_inference
from make_dataset import Recorder
from translator.execute import FPS
from translator.scene import TABLE_TOP, build, sample_layout
from translator.translate import load_card

OUT = ROOT / "outputs" / "eval"
SETTLE_S = 1.0
FALLBACK_LIMIT_S = 15.0
LIFT_MIN = 0.02  # cube centre this far above its resting height = lifted (tipping a 3 cm cube on its edge: 6 mm)
HELD_ABOVE = 0.006 + 0.005  # above the bowl floor (6 mm) by 5 mm = still held, as in run_skill
VIDEO_W, VIDEO_H = 960, 720  # main view; the policy's three 320x240 views are stacked on the right -> 1280x720


def load_policy(path, device, n_action_steps=None, temporal_ensemble=None):
    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.pretrained_path = path
    cfg.device = device
    if temporal_ensemble is not None:
        cfg.temporal_ensemble_coeff, cfg.n_action_steps = temporal_ensemble, 1
    elif n_action_steps is not None:
        cfg.n_action_steps = n_action_steps
    policy = get_policy_class(cfg.type).from_pretrained(path, config=cfg)
    policy.to(device).eval()
    pre, post = make_pre_post_processors(cfg, pretrained_path=str(path),
                                         preprocessor_overrides={"device_processor": {"device": device}})
    return cfg, policy, pre, post


def train_info(path):
    """The training run's dataset (from the checkpoint's train_config.json): root, robot, state names, episode lengths."""
    f = path / "train_config.json"
    if not f.exists():
        return None
    ds = json.loads(f.read_text())["dataset"]
    root = Path(ds["root"]) if ds.get("root") else None
    if root is not None and not root.is_absolute():
        root = next((r for r in (Path.cwd() / root, ROOT / root) if (r / "meta" / "info.json").exists()), None)
    if root is None or not (root / "meta" / "info.json").exists():
        return {"repo_id": ds["repo_id"], "root": ds.get("root"), "found": False}
    meta = LeRobotDatasetMetadata(ds["repo_id"], root=root)
    lengths = np.asarray(meta.episodes["length"], dtype=int)
    return {"repo_id": ds["repo_id"], "root": str(root), "found": True, "robot_type": meta.robot_type,
            "fps": meta.fps, "episodes": int(len(lengths)), "state_names": meta.features["observation.state"]["names"],
            "max_episode_s": round(float(lengths.max()) / meta.fps, 2), "mean_episode_s": round(float(lengths.mean()) / meta.fps, 2)}


def checkpoint_step(path):
    """'000300' for .../checkpoints/000300/pretrained_model (also through the 'last' link)."""
    parent = path.resolve().parent
    if parent.name.isdigit():
        return parent.name
    f = parent / "training_state" / "training_step.json"
    if f.exists():
        return f"{json.loads(f.read_text())['step']:06d}"
    return path.resolve().name


class Video:
    """Main view (free camera) on the left, the policy's own three camera images on the right."""

    def __init__(self, scene):
        self.scene = scene
        self.renderer = mujoco.Renderer(scene.model, VIDEO_H, VIDEO_W)
        self.font = ImageFont.load_default(size=22)
        self.small = ImageFont.load_default(size=16)
        self.frames = []

    def add(self, data, images, text):
        self.renderer.update_scene(data, camera=self.scene.camera())
        main = Image.fromarray(self.renderer.render())
        ImageDraw.Draw(main).text((12, 10), text, fill=(255, 255, 255), font=self.font, stroke_width=2, stroke_fill=(0, 0, 0))
        tiles = []
        for key, img in images.items():
            tile = Image.fromarray(img)
            ImageDraw.Draw(tile).text((6, 4), "policy sees: " + key.split(".")[-1], fill=(255, 255, 255), font=self.small,
                                      stroke_width=2, stroke_fill=(0, 0, 0))
            tiles.append(np.asarray(tile))
        self.frames.append(np.concatenate([np.asarray(main), np.concatenate(tiles, axis=0)], axis=1))

    def save(self, path):
        imageio.mimsave(path, self.frames, fps=FPS, codec="libx264", quality=7, macro_block_size=8,
                        ffmpeg_params=["-movflags", "+faststart"])
        self.frames = []

    def close(self):
        self.renderer.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("robot")
    p.add_argument("--card", default=str(ROOT / "cards" / "cube_to_bowl.json"))
    p.add_argument("--policy", required=True, help="a checkpoint's pretrained_model folder")
    p.add_argument("--trials", type=int, default=50)
    p.add_argument("--seed", type=int, default=5000, help="layout seed of trial 0; trial i uses seed + i")
    p.add_argument("--videos", type=int, default=0, help="save videos of the first N trials")
    p.add_argument("--max-seconds", type=float, default=None,
                   help="time limit per trial (default 1.5 x the longest training episode, else 15 s)")
    p.add_argument("--n-action-steps", type=int, default=None, help="actions run per policy call (default: checkpoint)")
    p.add_argument("--temporal-ensemble", type=float, default=None, metavar="COEFF",
                   help="ACT temporal ensembling (e.g. 0.01): query every tick and average the overlapping chunks")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args()
    torch.set_num_threads(2)  # batch of 1: more CPU threads only spin (12 cores busy and 3x slower with the default)

    path = Path(args.policy).expanduser().resolve()
    if not (path / "config.json").exists():
        sys.exit(f"{path} has no config.json; pass a checkpoint's pretrained_model folder")
    card = load_card(args.card)
    task = card["goal"]
    step = checkpoint_step(path)
    trained = train_info(path)

    scene = build(args.robot, card)
    rec = Recorder(scene, card, None)  # same state/camera definition and gripper calibration as make_dataset.py
    m, d = scene.model, scene.data
    phys_steps = round(1 / FPS / m.opt.timestep)

    cfg, policy, pre, post = load_policy(path, args.device, args.n_action_steps, args.temporal_ensemble)
    inputs = list(cfg.input_features)
    state_dim = cfg.input_features["observation.state"].shape[0] if "observation.state" in cfg.input_features else None
    action_dim = cfg.output_features["action"].shape[0]
    if state_dim not in (None, len(rec.names)) or action_dim != len(rec.names):
        sys.exit(f"policy state/action size {state_dim}/{action_dim} does not fit {args.robot} ({rec.names})")
    if trained and trained.get("found") and trained["state_names"] != rec.names:
        sys.exit(f"policy was trained on {trained['robot_type']} {trained['state_names']}, not {args.robot} {rec.names}")
    if trained and trained.get("found") and trained["fps"] != FPS:
        sys.exit(f"policy was trained at {trained['fps']} fps, the simulation runs at {FPS}")

    if args.max_seconds:
        limit_s, limit_from = args.max_seconds, "--max-seconds"
    elif trained and trained.get("found"):
        limit_s, limit_from = 1.5 * trained["max_episode_s"], f"1.5 x longest training episode ({trained['max_episode_s']} s)"
    else:
        limit_s, limit_from = FALLBACK_LIMIT_S, "fallback (training dataset not found)"
    n_ticks = round(limit_s * FPS)
    print(f"{args.robot} / {card['name']}: policy {cfg.type} step {step} on {args.device}, inputs {inputs}, "
          f"chunk {getattr(cfg, 'chunk_size', '-')}, n_action_steps {cfg.n_action_steps}"
          f"{f', temporal ensemble {cfg.temporal_ensemble_coeff}' if getattr(cfg, 'temporal_ensemble_coeff', None) else ''}")
    print(f"time limit {limit_s:.1f} s ({limit_from}) + {SETTLE_S:.0f} s settle; trials {args.trials} from seed {args.seed}")
    print(f"gripper travel open/closed: {np.round(rec.gripper.len_open, 4)} / {np.round(rec.gripper.len_shut, 4)}")

    image_keys = [k for k in inputs if k.startswith("observation.images.")]
    robot_type = trained.get("robot_type", args.robot) if trained else args.robot

    def act(state, images):
        obs = {"observation.state": state, **{k: images[k] for k in image_keys}}
        with torch.inference_mode():
            batch = prepare_observation_for_inference(obs, torch.device(args.device), task, robot_type)
            action = post(policy.select_action(pre(batch)))
        return action.squeeze(0).float().cpu().numpy()

    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{args.robot}_{card['name']}_{step}"
    if args.temporal_ensemble is not None:
        tag += f"_te{args.temporal_ensemble:g}"
    elif args.n_action_steps is not None:
        tag += f"_n{args.n_action_steps}"
    video = Video(scene) if args.videos else None
    rest = TABLE_TOP + scene.held_half
    rows, t_start = [], time.time()
    for i in range(args.trials):
        seed = args.seed + i
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
        scene.reset(cube, bowl, yaw)
        policy.reset()
        pre.reset()
        post.reset()
        start = scene.cube_pos()
        rise, held_near_bowl, in_bowl, grips = 0.0, False, [], []
        record = video is not None and i < args.videos
        t0 = time.time()

        def track():
            nonlocal rise, held_near_bowl
            c = scene.cube_pos()
            rise = max(rise, c[2] - rest)
            near = np.linalg.norm(c[:2] - scene.bowl_pos()[:2]) < scene.container_xy + 0.02
            held_near_bowl |= bool(near and c[2] - rest > HELD_ABOVE)
            in_bowl.append(scene.cube_in_bowl())

        for t in range(n_ticks):
            state, images = rec.observe(d.qpos)
            a = act(state, images)
            grip = float(np.clip(a[-1], 0.0, 1.0))
            grips.append(grip)
            if record:
                video.add(rec.render_data, images, f"trial {i}  seed {seed}  t {t / FPS:4.1f} s  grip {grip:.2f}")
            d.ctrl[rec.arm_acts] = a[:-1]
            scene.set_grip(grip)
            for _ in range(phys_steps):
                mujoco.mj_step(m, d)
            track()
        for t in range(round(SETTLE_S * FPS)):
            if record:
                state, images = rec.observe(d.qpos)
                video.add(rec.render_data, images, f"trial {i}  seed {seed}  settle (arm holds still)")
            for _ in range(phys_steps):
                mujoco.mj_step(m, d)
            track()

        success = scene.cube_in_bowl()
        if success:
            reason = "ok"
        elif held_near_bowl:
            reason = "near_bowl_outside"
        elif rise > LIFT_MIN:
            reason = "dropped"
        else:
            reason = "not_lifted"
        first_ok = None
        if success:
            k = len(in_bowl) - 1
            while k > 0 and in_bowl[k - 1]:
                k -= 1
            first_ok = round((k + 1) / FPS, 2)
        end = scene.cube_pos()
        row = {"seed": seed, "success": success, "reason": reason, "time_to_success_s": first_ok,
               "cube": np.round(cube, 4).tolist(), "bowl": np.round(bowl, 4).tolist(), "yaw_deg": round(math.degrees(yaw), 1),
               "max_lift_mm": round(rise * 1000, 1), "held_near_bowl": held_near_bowl,
               "cube_moved_mm": round(float(np.linalg.norm(end[:2] - start[:2])) * 1000, 1),
               "final_cube": np.round(end, 4).tolist(), "max_grip_cmd": round(max(grips), 3),
               "wall_s": round(time.time() - t0, 1)}
        rows.append(row)
        if record:
            name = OUT / f"{tag}_trial{i:02d}_seed{seed}_{reason}.mp4"
            video.save(name)
            row["video"] = str(name.relative_to(ROOT))
        print(f"trial {i:3d} seed {seed}: {'OK  ' if success else 'FAIL'} {reason:17s} lift {row['max_lift_mm']:6.1f} mm, "
              f"cube moved {row['cube_moved_mm']:6.1f} mm, max grip {row['max_grip_cmd']:.2f}"
              f"{f', in bowl from {first_ok:.1f} s' if success else ''}  ({row['wall_s']:.1f} s)", flush=True)

    if video:
        video.close()
    rec.close()
    ok = [r for r in rows if r["success"]]
    fails = {k: sum(r["reason"] == k for r in rows) for k in ("not_lifted", "dropped", "near_bowl_outside")}
    times = [r["time_to_success_s"] for r in ok]
    summary = {
        "robot": args.robot, "card": card["name"], "task": task, "policy": str(path), "policy_type": cfg.type,
        "checkpoint_step": step, "trials": len(rows), "first_seed": args.seed, "success": len(ok),
        "success_rate": round(len(ok) / max(1, len(rows)), 3), "fail_reasons": fails,
        "mean_time_to_success_s": round(float(np.mean(times)), 2) if times else None,
        "time_limit_s": round(limit_s, 2), "time_limit_from": limit_from, "settle_s": SETTLE_S,
        "n_action_steps": cfg.n_action_steps, "temporal_ensemble_coeff": getattr(cfg, "temporal_ensemble_coeff", None),
        "inputs": inputs, "state_names": rec.names, "device": args.device, "training_dataset": trained,
        "seconds_total": round(time.time() - t_start, 1),
        "fail_reason_meaning": {"not_lifted": f"cube never rose {LIFT_MIN * 100:.0f} cm (grasp missed, pushed, or never tried)",
                                "dropped": "lifted, but never held above/near the bowl",
                                "near_bowl_outside": "held near the bowl, but ended outside it"},
    }
    out = OUT / f"{tag}.json"
    out.write_text(json.dumps({"summary": summary, "trials": rows}, indent=1))
    print(f"\n{args.robot} {card['name']} step {step}: {len(ok)}/{len(rows)} success "
          f"({summary['success_rate'] * 100:.0f} %), fails {fails}, "
          f"mean time to success {summary['mean_time_to_success_s']} s, {summary['seconds_total']:.0f} s total")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
