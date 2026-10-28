"""Step 1: track the objects and the hand in a video with SAM 3.1, save tracks.json and an overlay video."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from translator.meta import sam_track

COLOURS = [(242, 183, 5), (40, 170, 90), (60, 140, 230), (220, 70, 60), (170, 90, 200)]


def overlay(video, tracks, out_path):
    reader = imageio.get_reader(video)
    fps = reader.get_meta_data().get("fps", 30)
    font = ImageFont.load_default(size=18)
    frames = []
    for i, frame in enumerate(reader):
        im = Image.fromarray(frame)
        draw = ImageDraw.Draw(im)
        for k, t in enumerate(tracks):
            colour = COLOURS[k % len(COLOURS)]
            for oid, (x1, y1, x2, y2, c) in t["frames"].get(i, {}).items():
                draw.rectangle([x1, y1, x2, y2], outline=colour, width=3)
                label = f"{t['prompt']} {oid}" + (f" {c:.2f}" if c is not None else "")
                draw.text((x1 + 4, max(0, y1 - 22)), label, fill=colour, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        draw.text((10, 10), f"frame {i}", fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        frames.append(np.asarray(im))
    imageio.mimsave(out_path, frames, fps=fps, codec="libx264", quality=7, macro_block_size=8)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--prompts", nargs="+", default=["lemon", "bowl", "hand"])
    p.add_argument("--out", default=None)
    args = p.parse_args()
    video = Path(args.video)
    out = Path(args.out) if args.out else ROOT / "outputs" / "jobs" / video.stem
    out.mkdir(parents=True, exist_ok=True)

    tracks, report = [], []
    for prompt in args.prompts:
        t0 = time.time()
        t = sam_track(video, prompt)
        ids = sorted({oid for boxes in t["frames"].values() for oid in boxes})
        print(f"{prompt!r}: {len(t['frames'])} frames with a match, object ids {ids}, "
              f"{time.time() - t0:.1f} s, cost ${t['cost_usd'] or 0:.4f}, usage {t['usage']}", flush=True)
        tracks.append(t)
        report.append({"prompt": prompt, "seconds": round(time.time() - t0, 1), "cost_usd": t["cost_usd"], "usage": t["usage"]})

    (out / "tracks.json").write_text(json.dumps(
        [{**t, "frames": {str(f): {str(o): b for o, b in boxes.items()} for f, boxes in t["frames"].items()}} for t in tracks]))
    (out / "sam_report.json").write_text(json.dumps(report, indent=1))
    overlay(video, tracks, out / "tracks_overlay.mp4")
    print("saved", out / "tracks.json", "and", out / "tracks_overlay.mp4")


if __name__ == "__main__":
    main()
