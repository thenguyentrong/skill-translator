"""A silent run recording: the phone video with SAM 3.1 boxes, the skill card Muse wrote, then every robot doing it.

  make_reel.py --job outputs/jobs/lemon_into_bowl_1cycle                      # the job's own robot clips -> <job>/reel.mp4
  make_reel.py --job outputs/jobs/lemon_into_bowl_1cycle --skill lemon_to_bowl  # matrix clips -> outputs/reel/<skill>.mp4
  make_reel.py --poster                                                       # skills x robots -> outputs/reel/matrix.png
  make_reel.py --robot oli --cols 4                                           # one robot, every skill -> outputs/reel/robot_oli.mp4
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS = 25
W, H = 1920, 1080
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BG = (18, 20, 24)


def fit(frame, w=W, h=H):
    im = Image.fromarray(frame)
    s = min(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), BG)
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def caption(im, text, size=34):
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(SANS, size)
    d.text((40, H - 70), text, fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0))
    return np.asarray(im)


def video_frames(path, text, fps=FPS):
    r = imageio.get_reader(path)
    src = r.get_meta_data().get("fps", fps)
    frames = [f for f in r]
    idx = np.round(np.arange(0, len(frames), src / fps)).astype(int)
    return [caption(fit(frames[min(i, len(frames) - 1)]), text) for i in idx]


def card_frames(card, seconds=5.0):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((60, 40), "2. Muse Spark watches it and writes the skill card", fill=(242, 183, 5), font=ImageFont.truetype(SANS, 40))
    o = card["objects"]
    lines = [f"goal:     {card['goal']}", ""]
    if card.get("kind") == "open":
        return _open_card_frames(card, im, d, lines, seconds)
    if card.get("kind") == "carry":
        return _carry_card_frames(card, im, d, lines, seconds)
    for name, spec in o.items():
        extra = (f"size {', '.join(f'{v * 100:.1f}' for v in spec['size'])} cm" if "size" in spec
                 else f"inner radius {spec['inner_radius'] * 100:.0f} cm, wall {spec['wall_height'] * 100:.0f} cm")
        lines.append(f"object:   {name} ({spec['shape']}, {extra})")
    g = card["grip"]
    lines += [f"grip:     from the {g['approach']}, {g['between']}, {g['width'] * 100:.1f} cm wide", "", "steps:"]
    for s in card["steps"]:
        what = s.get("object") or s.get("into") or (f"{s['height'] * 100:.0f} cm" if "height" in s else "")
        lines.append(f"  {s['do']:8s} {what}")
    lines += ["", f"success:  {card['success']['object']} {card['success']['test']} {card['success']['container']}"]
    d.multiline_text((60, 130), "\n".join(lines), fill=(230, 230, 230), font=ImageFont.truetype(MONO, 34), spacing=12)
    frame = np.asarray(im)
    return [frame] * round(seconds * FPS)


def _open_card_frames(card, im, d, lines, seconds):
    cab, handle = card["success"]["object"], card["grip"]["object"]
    c, h = card["objects"][cab], card["objects"][handle]
    door = c["door"]
    lines += [f"object:   {cab} ({', '.join(f'{v * 100:.0f}' for v in c['size'])} cm), door hinged on the {door['hinge']}",
              f"object:   {handle} (bar, {h['diameter'] * 1000:.0f} mm thick, {h['length'] * 100:.0f} cm long)",
              f"grip:     from the {card['grip']['approach']}, {card['grip']['between']}", "", "steps:"]
    lines += [f"  {s['do']:8s} {s.get('object', '')}" for s in card["steps"]]
    lines += ["", f"success:  {cab} door open at least {card['success']['min_angle_deg']} degrees"]
    d.multiline_text((60, 130), "\n".join(lines), fill=(230, 230, 230), font=ImageFont.truetype(MONO, 34), spacing=12)
    return [np.asarray(im)] * round(seconds * FPS)


def _carry_card_frames(card, im, d, lines, seconds):
    crate, place = card["grip"]["object"], card["success"]["place"]
    c, p, n = card["objects"][crate], card["objects"][place], card.get("needs", {})
    h = c["handle"]
    handles = "a handle on each side" if c["handles"] == "side" else "one handle on top"
    lines += [f"object:   {crate} ({', '.join(f'{v * 100:.0f}' for v in c['size'])} cm, {c['mass']:.1f} kg), {handles}",
              f"place:    {place}, {p['distance']:.1f} m to the {p.get('side', 'left')}",
              f"grip:     the handle{'s' if c['handles'] == 'side' else ''} from the top, bar {h['diameter'] * 1000:.0f} mm",
              f"needs:    {n.get('hands', 1)} hand{'s' if n.get('hands', 1) > 1 else ''}, moves {n.get('move_m', 0):.1f} m"
              f"{', keep upright' if n.get('keep_upright') else ''}", "", "steps:"]
    for s in card["steps"]:
        what = s.get("object") or s.get("to") or (f"{s['height'] * 100:.0f} cm" if "height" in s else "")
        lines.append(f"  {s['do']:8s} {what}")
    lines += ["", f"success:  {crate} on {place}, within {card['success'].get('within', 0.1) * 100:.0f} cm, upright"]
    d.multiline_text((60, 130), "\n".join(lines), fill=(230, 230, 230), font=ImageFont.truetype(MONO, 34), spacing=12)
    return [np.asarray(im)] * round(seconds * FPS)


def grid_frames(paths, cols, title):
    readers = [imageio.get_reader(p) for p in paths]
    clips = [[f for f in r] for r in readers]
    src = readers[0].get_meta_data().get("fps", FPS / 2)
    n = max(len(c) for c in clips)
    rows = -(-len(clips) // cols)
    cw, ch = W // cols, (H - 90) // rows
    out = []
    font = ImageFont.truetype(SANS, 38)
    for i in np.round(np.arange(0, n, src / FPS)).astype(int):
        im = Image.new("RGB", (W, H), BG)
        ImageDraw.Draw(im).text((40, 22), title, fill=(255, 255, 255), font=font)
        for k, c in enumerate(clips):
            tile = Image.fromarray(c[min(i, len(c) - 1)])
            s = min(cw / tile.width, ch / tile.height)
            tile = tile.resize((int(tile.width * s), int(tile.height * s)), Image.LANCZOS)
            x, y = (k % cols) * cw + (cw - tile.width) // 2, 90 + (k // cols) * ch + (ch - tile.height) // 2
            im.paste(tile, (x, y))
        out.append(np.asarray(im))
    out += [out[-1]] * FPS
    return out


def poster(out, tw=320, th=240):
    """Skills x robots: a frame from each cell's first trial and its success count."""
    data = json.loads((ROOT / "outputs" / "matrix" / "matrix.json").read_text())
    rows = data["rows"]
    skills = data.get("skills") or sorted({r["skill"] for r in rows})
    robots = data.get("robots") or list(dict.fromkeys(r["robot"] for r in rows))
    by = {(r["skill"], r["robot"]): r for r in rows}
    left, top = 270, 60
    im = Image.new("RGB", (left + tw * len(robots), top + th * len(skills)), BG)
    d = ImageDraw.Draw(im)
    head, big = ImageFont.truetype(SANS, 26), ImageFont.truetype(SANS, 44)
    for j, rb in enumerate(robots):
        d.text((left + j * tw + 12, 18), rb, fill=(255, 255, 255), font=head)
    for i, sk in enumerate(skills):
        d.text((16, top + i * th + th // 2 - 16), sk, fill=(255, 255, 255), font=head)
        for j, rb in enumerate(robots):
            r = by.get((sk, rb))
            card = ROOT / "cards" / f"{sk}.json"
            kind = json.loads(card.read_text()).get("kind") if card.exists() else None
            opening = kind == "open"
            clip = ROOT / "outputs" / "matrix" / f"{sk}__{rb}.mp4"
            if clip.exists():
                frames = [f for f in imageio.get_reader(clip)]
                tile = Image.fromarray(frames[int({"open": 0.8, "carry": 0.97}.get(kind, 0.62) * len(frames))]).resize((tw - 6, th - 6))
                im.paste(tile, (left + j * tw + 3, top + i * th + 3))
            room = "cabinet does\nnot fit its reach" if opening else "container does\nnot fit its reach"
            cannot = r and {"too_big": "too big\nfor its gripper", "too_thin": "handle too thin\nfor its gripper",
                            "no_room": room, "two_hands": "needs two hands", "must_walk": "needs to walk",
                            "too_heavy": "too heavy\nfor its arm", "two_hand_grip": "two hands without\nhandles: not yet",
                            "handle_too_high": "handle too high\nfor its hand", "handle_too_low": "handle too low\nfor its hand"}.get(next((k for k, v in r["fails"].items() if v == r["n"]), None))
            if cannot:
                d.rectangle([left + j * tw + 3, top + i * th + 3, left + (j + 1) * tw - 3, top + (i + 1) * th - 3], fill=BG)
                d.text((left + j * tw + 14, top + i * th + th // 2 - 40), cannot, fill=(154, 164, 171), font=head, spacing=6)
            elif r:
                rate = r["success"] / r["n"]
                colour = (60, 200, 110) if rate >= 0.8 else (242, 183, 5) if rate >= 0.5 else (230, 80, 70)
                d.text((left + j * tw + 14, top + i * th + th - 62), f"{r['success']}/{r['n']}", fill=colour, font=big,
                       stroke_width=3, stroke_fill=(0, 0, 0))
    im.save(out)
    print("saved", out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--skill")
    p.add_argument("--poster", action="store_true", help="only make outputs/reel/matrix.png from the matrix run")
    p.add_argument("--job", help="job folder from run_job.py (SAM overlay, card); without --skill its own robot clips")
    p.add_argument("--robots", nargs="*")
    p.add_argument("--robot", help="one robot's matrix clips of every skill")
    p.add_argument("--cols", type=int, default=3)
    args = p.parse_args()
    if args.poster:
        (ROOT / "outputs" / "reel").mkdir(parents=True, exist_ok=True)
        return poster(ROOT / "outputs" / "reel" / "matrix.png")
    if args.robot:
        return robot_reel(args.robot, args.cols)
    make(args.skill, Path(args.job) if args.job else None, args.robots, args.cols)


def robot_reel(robot, cols=4):
    rows = {r["skill"]: r for r in json.loads((ROOT / "outputs" / "matrix" / "matrix.json").read_text())["rows"] if r["robot"] == robot}
    clips = [c for c in sorted((ROOT / "outputs" / "matrix").glob(f"*__{robot}.mp4")) if c.stem.split("__")[0] in rows]
    said_no = ("too_big", "too_thin", "no_room", "two_hands", "must_walk", "too_heavy", "two_hand_grip", "handle_too_high",
               "handle_too_low")
    tried = [r for r in rows.values() if not any(v == r["n"] and k in said_no for k, v in r["fails"].items())]
    title = f"{robot}: every skill in the library, {sum(r['success'] for r in tried)}/{sum(r['n'] for r in tried)} tries passed"
    out = ROOT / "outputs" / "reel" / f"robot_{robot}.mp4"
    imageio.mimsave(out, grid_frames(clips, cols, title), fps=FPS, codec="libx264", quality=7, macro_block_size=8)
    print("saved", out, f"{len(clips)} clips")


def make(skill=None, job=None, robots=None, cols=3):
    """With a job folder: its SAM overlay, its card and its robot clips. Without: the matrix clips of `skill`."""
    if job is not None and skill is None:
        clips = sorted(job.glob("*_trial0_*.mp4"))
        card = json.loads((job / "card.json").read_text())
        name, out = card["name"], job / "reel.mp4"
    else:
        clips = sorted((ROOT / "outputs" / "matrix").glob(f"{skill}__*.mp4"))
        card = json.loads((ROOT / "cards" / f"{skill}.json").read_text())
        name, out = skill, ROOT / "outputs" / "reel" / f"{skill}.mp4"
    if robots:
        clips = [c for r in robots for c in clips if c.stem.split("__")[-1] == r or c.stem.startswith(f"{r}_trial0")]
    frames = []
    if job is not None:
        frames += video_frames(job / "tracks_overlay.mp4", "1. A short video of a hand doing the task. SAM 3.1 tracks the objects and the hand.")
        frames += card_frames(card)
    frames += grid_frames(clips, cols, f"{'3. ' if job is not None else ''}{len(clips)} robots, each in its own way")
    out.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(out, frames, fps=FPS, codec="libx264", quality=7, macro_block_size=8,
                    ffmpeg_params=["-movflags", "+faststart"])
    print("saved", out, f"{len(frames) / FPS:.1f} s")
    return out


if __name__ == "__main__":
    main()
