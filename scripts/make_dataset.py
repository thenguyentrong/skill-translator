"""Record successful skill runs as a LeRobot dataset (one per robot): arm state, action, 3 camera images, task.

Each try: random layout (seed) -> camera eyes -> run_skill in full physics. Only runs that pass the card's success
test are saved. Frame t = the state before control tick t (+ its camera images) and the command sent during tick t.
"""
import argparse
import json
import math
import os
import shutil
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("SVT_LOG", "1")
warnings.filterwarnings("ignore", message="Cannot enable progress bars")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mujoco
import numpy as np

from kill_test import sample_layout
from translator.execute import FPS, run_skill
from translator.perceive import Eyes
from translator.scene import CAMERAS, PREFIX, build
from translator.translate import load_card

HEIGHT, WIDTH = 240, 320


def cam_key(cam):
    return "observation.images." + cam.removeprefix(PREFIX)


class Gripper:
    """The gripper as one number, 0 = open .. 1 = closed, for any gripper (one motor or a hand of several)."""

    def __init__(self, scene, steps=400):
        self.ids = list(scene.gripper_ids)
        n = len(self.ids)
        self.opened = np.broadcast_to(np.asarray(scene.open_ctrl, dtype=float), (n,)).copy()
        self.shut = np.broadcast_to(np.atleast_1d(scene.robot.gripper_closed).astype(float), (n,)).copy()
        self.ref = int(np.argmax(np.abs(self.shut - self.opened)))
        self.len_open = self._settle(scene, self.opened, steps)
        self.len_shut = self._settle(scene, self.shut, steps)
        self.moves = np.abs(self.len_shut - self.len_open) > 1e-6

    def _settle(self, scene, ctrl, steps):
        m = scene.model
        d = mujoco.MjData(m)
        mujoco.mj_copyData(d, m, scene.data)
        d.ctrl[self.ids] = ctrl
        for _ in range(steps):
            mujoco.mj_step(m, d)
        return d.actuator_length[self.ids].copy()

    def command(self, ctrl):
        """Recover the 0..1 grip command from the gripper motor targets."""
        i = self.ref
        return float((ctrl[self.ids[i]] - self.opened[i]) / (self.shut[i] - self.opened[i]))

    def state(self, data):
        """How far the gripper is closed, from the motors' measured travel (stays < 1 when it holds the cube)."""
        frac = (data.actuator_length[self.ids] - self.len_open) / np.where(self.moves, self.len_shut - self.len_open, 1.0)
        return float(np.clip(frac[self.moves], 0.0, 1.0).mean()) if self.moves.any() else 0.0


class Recorder:
    def __init__(self, scene, card, eyes):
        self.scene, self.card, self.eyes = scene, card, eyes
        m = scene.model
        self.arm_acts = [a for a in scene.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
        self.arm_qadr = [int(m.jnt_qposadr[m.actuator_trnid[a, 0]]) for a in self.arm_acts]
        self.names = [m.joint(int(m.actuator_trnid[a, 0])).name.removeprefix(PREFIX) for a in self.arm_acts] + ["gripper"]
        self.gripper = Gripper(scene)
        self.renderer = mujoco.Renderer(m, HEIGHT, WIDTH)
        self.render_data = mujoco.MjData(m)

    def features(self):
        vec = {"dtype": "float32", "shape": (len(self.names),), "names": self.names}
        out = {"observation.state": dict(vec), "action": dict(vec)}
        for cam in CAMERAS:
            out[cam_key(cam)] = {"dtype": "video", "shape": (HEIGHT, WIDTH, 3), "names": ["height", "width", "channels"]}
        return out

    def run(self, seed):
        """One try. Returns (history, actions, info); history/actions are None when the run fails."""
        scene, d = self.scene, self.scene.data
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
        scene.reset(cube, bowl, yaw)
        info = {"seed": seed, "cube": np.round(cube, 4).tolist(), "bowl": np.round(bowl, 4).tolist(),
                "yaw_deg": round(math.degrees(yaw), 2)}
        seen = self.eyes.find(self.card) if self.eyes else scene.true_objects()
        if any(v is None for v in seen.values()):
            return None, None, {**info, "reason": "unseen"}
        actions = []

        def on_tick(_label):
            actions.append(np.append(d.ctrl[self.arm_acts], self.gripper.command(d.ctrl)).astype(np.float32))

        try:
            res = run_skill(scene, self.card, seen, on_tick=on_tick)
        except Exception as e:  # a bad layout must not end a long unattended run
            return None, None, {**info, "reason": f"error: {type(e).__name__}: {e}"}
        if not res.success:
            return None, None, {**info, "reason": res.reason}
        assert len(res.history) == len(actions) + 1, (len(res.history), len(actions))
        return res.history[:-1], actions, {**info, "reason": "ok", "frames": len(actions)}

    def observe(self, qpos):
        """What the policy sees at sim state `qpos`: arm joint angles + gripper closure (float32), and the 3 camera
        images (uint8 HxWx3, no labels). Also used by eval_policy.py, so recording and evaluation see the same thing."""
        m, d = self.scene.model, self.render_data
        d.qpos[:] = qpos
        mujoco.mj_forward(m, d)
        state = np.append(d.qpos[self.arm_qadr], self.gripper.state(d)).astype(np.float32)
        images = {}
        for cam in CAMERAS:
            self.renderer.update_scene(d, camera=cam)
            images[cam_key(cam)] = self.renderer.render()
        return state, images

    def frames(self, history, actions, task):
        for q, a in zip(history, actions):
            state, images = self.observe(q)
            yield {"observation.state": state, "action": a, "task": task, **images}

    def close(self):
        self.renderer.close()
        if self.eyes:
            self.eyes.close()


def generate(args, out):
    import av
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    av.logging.set_libav_level(av.logging.ERROR)
    card = load_card(args.card)
    scene = build(args.robot, card)
    rec = Recorder(scene, card, Eyes(scene) if args.eyes == "camera" else None)
    print(f"{args.robot}: state/action = {rec.names}  (gripper 0 open .. 1 closed)")
    print(f"gripper travel open/closed: {np.round(rec.gripper.len_open, 4)} / {np.round(rec.gripper.len_shut, 4)}")
    ds = LeRobotDataset.create(repo_id=f"local/{out.name}", fps=FPS, features=rec.features(), root=out,
                               robot_type=args.robot, use_videos=True, image_writer_threads=args.image_threads)
    task = card["goal"]
    saved, tries, fails, t_sim, t_rec, t_start = [], [], {}, 0.0, 0.0, time.time()
    max_tries = args.max_tries or 2 * args.episodes + 10
    seed = args.seed
    while len(saved) < args.episodes and len(tries) < max_tries:
        t0 = time.time()
        history, actions, info = rec.run(seed)
        t1 = time.time()
        t_sim += t1 - t0
        tries.append(info)
        seed += 1
        if history is None:
            fails[info["reason"]] = fails.get(info["reason"], 0) + 1
            print(f"seed {info['seed']:4d}: FAIL {info['reason']}  ({t1 - t0:.1f} s)", flush=True)
            continue
        for frame in rec.frames(history, actions, task):
            ds.add_frame(frame)
        ds.save_episode()
        t2 = time.time()
        t_rec += t2 - t1
        saved.append({"episode_index": len(saved), **info})
        print(f"seed {info['seed']:4d}: ok  episode {len(saved) - 1:3d}, {info['frames']} frames  "
              f"(sim {t1 - t0:.1f} s, render+encode {t2 - t1:.1f} s)", flush=True)
    ds.finalize()
    rec.close()
    wall = time.time() - t_start
    summary = {
        "robot": args.robot, "card": card["name"], "task": task, "eyes": args.eyes, "first_seed": args.seed,
        "episodes_saved": len(saved), "tries": len(tries), "success_rate": round(len(saved) / max(1, len(tries)), 3),
        "fail_reasons": fails, "frames": int(sum(e["frames"] for e in saved)), "fps": FPS, "image_hw": [HEIGHT, WIDTH],
        "seconds_total": round(wall, 1), "seconds_per_saved_episode": round(wall / max(1, len(saved)), 2),
        "seconds_sim": round(t_sim, 1), "seconds_render_encode": round(t_rec, 1),
        "state_names": rec.names, "gripper": "0 = open, 1 = closed (action: command sent; state: measured travel)",
    }
    (out / "generation.json").write_text(json.dumps({"summary": summary, "episodes": saved, "tries": tries}, indent=1))
    print("\n" + json.dumps(summary, indent=1))
    if len(saved) < args.episodes:
        print(f"WARNING: only {len(saved)}/{args.episodes} episodes after {len(tries)} tries")


def dir_size(path):
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


def verify(out):
    """Load the dataset back from disk, check shapes, decode every camera, save a sample image grid."""
    from PIL import Image, ImageDraw
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(f"local/{out.name}", root=out)
    print(f"\nloaded {out}: {ds.num_episodes} episodes, {ds.num_frames} frames, fps {ds.fps}, "
          f"{dir_size(out) / 1e6:.1f} MB on disk")
    print("features:", {k: tuple(v["shape"]) for k, v in ds.features.items()})
    ep = ds.meta.episodes
    lengths = [int(ep[i]["length"]) for i in range(ds.num_episodes)]
    print(f"episode length: min {min(lengths)}, mean {np.mean(lengths):.0f}, max {max(lengths)} frames "
          f"({min(lengths) / ds.fps:.1f}-{max(lengths) / ds.fps:.1f} s)")
    n_state = ds.features["observation.state"]["shape"][0]
    item = ds[0]
    print("tasks:", ds.meta.tasks.index.tolist(), "| frame 0 task:", repr(item["task"]))
    print(f"frame 0 state {tuple(item['observation.state'].shape)}: {np.round(item['observation.state'].numpy(), 3)}")
    print(f"frame 0 action {tuple(item['action'].shape)}: {np.round(item['action'].numpy(), 3)}")
    for key in ds.meta.video_keys:
        img = item[key]
        assert tuple(img.shape) == (3, HEIGHT, WIDTH), (key, img.shape)
        print(f"{key}: decoded {tuple(img.shape)} {img.dtype}, range {img.min():.2f}..{img.max():.2f}")
    assert tuple(item["observation.state"].shape) == (n_state,) and tuple(item["action"].shape) == (n_state,)

    start, end = int(ep[0]["dataset_from_index"]), int(ep[0]["dataset_to_index"])
    states = np.stack([ds.hf_dataset[i]["observation.state"] for i in range(start, end)])
    actions = np.stack([ds.hf_dataset[i]["action"] for i in range(start, end)])
    track = np.abs(actions[:-1, :-1] - states[1:, :-1])
    print(f"episode 0: arm |action(t) - state(t+1)| mean {track.mean():.4f} rad, max {track.max():.4f} rad; "
          f"gripper cmd max {actions[:, -1].max():.2f}, gripper state max {states[:, -1].max():.2f}")

    rows = []
    font_h = 16
    for frac in (0.0, 0.3, 0.55, 0.8, 1.0):
        idx = start + min(end - start - 1, round(frac * (end - start - 1)))
        it = ds[idx]
        tiles = [(it[k].permute(1, 2, 0).numpy() * 255).astype(np.uint8) for k in ds.meta.video_keys]
        rows.append(np.concatenate(tiles, axis=1))
    grid = Image.fromarray(np.concatenate(rows, axis=0))
    header = Image.new("RGB", (grid.width, font_h + 6), (255, 255, 255))
    draw = ImageDraw.Draw(header)
    for i, k in enumerate(ds.meta.video_keys):
        draw.text((i * WIDTH + 6, 4), f"{k.split('.')[-1]}  (episode 0, t = 0 / 30 / 55 / 80 / 100 %)", fill=(0, 0, 0))
    sheet = Image.new("RGB", (grid.width, grid.height + header.height))
    sheet.paste(header, (0, 0))
    sheet.paste(grid, (0, header.height))
    sheet.save(out / "sample.png")
    print(f"saved {out / 'sample.png'}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("robot")
    p.add_argument("--card", default=str(ROOT / "cards" / "cube_to_bowl.json"))
    p.add_argument("--episodes", type=int, default=50, help="successful episodes to save")
    p.add_argument("--max-tries", type=int, default=None, help="stop after this many tries (default 2 * episodes + 10)")
    p.add_argument("--seed", type=int, default=0, help="first layout seed; each try uses the next one")
    p.add_argument("--out", default=None, help="dataset folder (default outputs/datasets/<robot>_<card name>)")
    p.add_argument("--eyes", choices=["camera", "sim"], default="camera")
    p.add_argument("--image-threads", type=int, default=4)
    p.add_argument("--overwrite", action="store_true", help="delete an existing dataset at --out first")
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    card_name = load_card(args.card)["name"]
    out = Path(args.out or ROOT / "outputs" / "datasets" / f"{args.robot}_{card_name}").resolve()
    if not args.verify_only:
        if out.exists():
            if not args.overwrite:
                sys.exit(f"{out} exists; pass --overwrite to replace it")
            if any(out.iterdir()) and not (out / "meta" / "info.json").exists():
                sys.exit(f"{out} is not a LeRobot dataset; not deleting it")
            shutil.rmtree(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        generate(args, out)
    verify(out)


if __name__ == "__main__":
    main()
