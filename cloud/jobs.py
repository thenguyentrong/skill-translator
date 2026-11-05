"""The worker steps as plain functions: modal_app.py runs them in the cloud."""
import json
import subprocess
import time
from pathlib import Path

FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm"
MAX_SECONDS = 15
SORRY = "This video could not be used. Try a short clip of one hand moving one object into something."


class NotUsable(Exception):
    """The message is safe to show to the person who uploaded the video."""


def prepare(raw, clip):
    """Any phone video -> H.264 mp4, at most 15 s and 1280 px, no sound, what the card stage expects.
    Only local files and video containers are allowed, so a crafted playlist file cannot make ffmpeg fetch anything."""
    safe = ["-protocol_whitelist", "file", "-format_whitelist", FORMATS]
    probe = subprocess.run(["ffprobe", "-v", "error", *safe, "-show_entries", "format=duration:stream=codec_type",
                            "-of", "json", str(raw)], capture_output=True, text=True, timeout=30)
    info = json.loads(probe.stdout or "{}") if probe.returncode == 0 else {}
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise NotUsable("This file is not a video we can read. Try an mp4 or mov.")
    if float(info.get("format", {}).get("duration") or 0) < 1:
        raise NotUsable("This video is too short.")
    size = "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    done = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *safe, "-i", str(raw), "-map", "0:v:0", "-t", str(MAX_SECONDS),
                           "-vf", size, "-fpsmax", "30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(clip)], capture_output=True, timeout=150)
    if done.returncode or not Path(clip).exists():
        raise NotUsable("This file is not a video we can read. Try an mp4 or mov.")


def make_card(clip, out, save):
    """The card stage, then every robot's yes or no. `save` gets each new piece of the job's state."""
    from run_job import check, learn
    from translator.robots import ROBOTS
    stages = []

    def stage(name, t0, cost=None, **_):
        stages.append({"stage": name, "seconds": round(time.time() - t0, 1), "cost_usd": cost})
        save(state="reading", stages=stages)

    save(state="reading")
    card = learn(clip, out, stage)
    if card is None:
        raise NotUsable("No object moved far enough in this video. Try a clip where one object clearly moves.")
    muse = json.loads((out / "card_muse.json").read_text())
    save(state="checking", card=card, evidence=muse.get("evidence"), overlay="tracks_overlay.mp4")
    answers = {}
    for robot in ROBOTS:
        if not robot.endswith("_muse"):
            answers[robot] = check(robot, card)
    save(state="ready", check=answers)


def try_one(card, robot, out, trials):
    """Returns the score ('4/5') or why the robot could not start, and the name of the first try's clip."""
    from run_job import try_robot
    result = try_robot(robot, card, out, trials)
    clip = next(iter(sorted(out.glob(f"{robot}_trial0_*.mp4"))), None)
    return {"result": result, "clip": clip.name if clip else None}
