"""Renders the README media: hero.gif / hero.mp4 (one skill card, four robots), robots.png, vision.png."""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from kill_test import sample_layout
from translator.execute import FPS, run_skill
from translator.perceive import Eyes
from translator.scene import PREFIX, TABLE_TOP, build
from translator.translate import load_card

OUT = ROOT / "docs" / "media"
CARD = load_card(ROOT / "cards" / "cube_to_bowl.json")
NAMES = {"so101": "SO-101", "panda": "Franka Panda", "ur5e": "UR5e + Robotiq", "g1": "Unitree G1"}
W, H = 480, 360


def font(size):
    return ImageFont.load_default(size=size)


def label(img, text, size=22):
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((12, 8), text, fill=(255, 255, 255), font=font(size), stroke_width=3, stroke_fill=(20, 20, 20))
    return np.asarray(im)


def close_camera(scene, distance=1.6, azimuth=145, elevation=-22, lift=0.1):
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [scene.origin[0] + 0.45 * scene.reach, scene.origin[1], TABLE_TOP + lift * scene.reach + 0.03]
    cam.distance = distance * scene.reach + 0.25
    cam.azimuth, cam.elevation = azimuth, elevation
    return cam


def hero(robots=("so101", "panda", "ur5e", "g1"), seed=2, every=2):
    panels = []
    for name in robots:
        scene = build(name)
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
        scene.reset(cube, bowl, yaw)
        eyes = Eyes(scene)
        res = run_skill(scene, CARD, eyes.find(CARD))
        eyes.close()
        m, d = scene.model, mujoco.MjData(scene.model)
        cam = close_camera(scene)
        frames = []
        with mujoco.Renderer(m, H, W) as main, mujoco.Renderer(m, 120, 160) as wrist:
            for q in res.history[::every]:
                d.qpos[:] = q
                mujoco.mj_forward(m, d)
                main.update_scene(d, camera=cam)
                img = main.render().copy()
                wrist.update_scene(d, camera=PREFIX + "wrist")
                inset = label(wrist.render(), "wrist cam", 14)
                img[H - 128:H - 8, W - 168:W - 8] = inset
                frames.append(label(img, NAMES[name] + ("" if res.success else f"  (fail: {res.reason})")))
        print(name, "ok" if res.success else res.reason, len(frames), "frames", flush=True)
        panels.append(frames)
    n = max(len(p) for p in panels) + FPS // every
    panels = [p + [p[-1]] * (n - len(p)) for p in panels]
    frames = [np.concatenate([np.concatenate([p[i] for p in panels[:2]], axis=1),
                              np.concatenate([p[i] for p in panels[2:]], axis=1)], axis=0) for i in range(n)]
    imageio.mimsave(OUT / "hero.mp4", frames, fps=FPS / every, codec="libx264", quality=8, macro_block_size=8,
                    ffmpeg_params=["-movflags", "+faststart"])
    small = [np.asarray(Image.fromarray(f).resize((f.shape[1] * 2 // 3, f.shape[0] * 2 // 3), Image.LANCZOS)) for f in frames]
    imageio.mimsave(OUT / "hero.gif", small, duration=1000 * every / FPS, loop=0)


def robots_still(robots=("so101", "panda", "ur5e", "g1")):
    tiles = []
    for name in robots:
        scene = build(name)
        with mujoco.Renderer(scene.model, H, W) as r:
            r.update_scene(scene.data, camera=close_camera(scene, distance=2.2, lift=0.45))
            tiles.append(label(r.render(), NAMES[name]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[:2], 1), np.concatenate(tiles[2:], 1)], 0)).save(OUT / "robots.png")


def project(model, data, camera, pts, w, h):
    cam = model.camera(camera).id
    f = 0.5 * h / math.tan(math.radians(model.cam_fovy[cam]) / 2)
    local = (pts - data.cam_xpos[cam]) @ data.cam_xmat[cam].reshape(3, 3)
    return np.stack([f * local[:, 0] / -local[:, 2] + w / 2, -f * local[:, 1] / -local[:, 2] + h / 2], axis=1)


def vision_still(name="so101", seed=0):
    scene = build(name)
    cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
    scene.reset(cube, bowl, yaw)
    eyes = Eyes(scene, W, H)
    seen = eyes.find(CARD)
    m, d = scene.model, scene.data
    eyes.rgb.update_scene(d, camera="front")
    im = Image.fromarray(eyes.rgb.render().copy())
    draw = ImageDraw.Draw(im)
    for i, (obj, colour) in enumerate((("cube", (255, 230, 0)), ("bowl", (255, 255, 255)))):
        pts = eyes.points(obj)
        for u, v in project(m, d, "front", pts[::3], W, H):
            draw.point((u, v), fill=colour)
        cx, cy = project(m, d, "front", seen[obj]["pos"][None], W, H)[0]
        draw.line([(cx - 14, cy), (cx + 14, cy)], fill=colour, width=3)
        draw.line([(cx, cy - 14), (cx, cy + 14)], fill=colour, width=3)
        err = np.linalg.norm(seen[obj]["pos"][:2] - scene.true_objects()[obj]["pos"][:2]) * 1000
        text = f"+ {obj}: found {err:.1f} mm from the true spot" + (f", turned {math.degrees(seen[obj]['yaw']):.0f}°" if obj == "cube" else "")
        draw.text((12, H - 56 + 24 * i), text, fill=colour, font=font(17), stroke_width=3, stroke_fill=(20, 20, 20))
    left = label(np.asarray(im), "front camera: what the robot sees")
    res = run_skill(scene, CARD, seen)
    grasp = next(i for i, q in enumerate(res.history) if i > 5 and np.linalg.norm(q[scene.cube_qadr + 2] - TABLE_TOP) > 0.03)
    d2 = mujoco.MjData(m)
    d2.qpos[:] = res.history[grasp]
    mujoco.mj_forward(m, d2)
    with mujoco.Renderer(m, H, W) as r:
        r.update_scene(d2, camera=PREFIX + "wrist")
        right = label(r.render(), "wrist camera: cube in the gripper")
    eyes.close()
    Image.fromarray(np.concatenate([left, right], 1)).save(OUT / "vision.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    vision_still()
    robots_still()
    hero()
    for f in sorted(OUT.iterdir()):
        print(f.name, f"{f.stat().st_size / 1e6:.1f} MB")
