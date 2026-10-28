"""Local web app: a JSON API over the job folders + the static page in web/static/.

  scripts/web.sh            # or: .venv/bin/python -m web.app   -> http://127.0.0.1:8000

The server never runs MuJoCo or calls the Meta API itself: it starts `web.worker` (or scripts/train_job.py) processes
and reads the files they write in outputs/jobs/<video>/ and outputs/train_jobs/<card>/. That keeps the page and the
API apart, so the page can move to static hosting and the workers to cloud GPUs later.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JOBS = ROOT / "outputs" / "jobs"
TRAIN = ROOT / "outputs" / "train_jobs"
VIDEOS = ROOT / "data" / "videos"
PY = ROOT / ".venv" / "bin" / "python"
ENV = {**os.environ, "MUJOCO_GL": "egl", "HF_HUB_OFFLINE": "1"}
MAX_SECONDS = 15
THUMBS = ROOT / "outputs" / "web" / "thumbs"

app = FastAPI(title="Translator")
procs = {}  # (job, step) -> Popen


def running(job, step):
    p = procs.get((job, step))
    return p is not None and p.poll() is None


def start(job, step, cmd):
    if running(job, step):
        raise HTTPException(409, f"{step} is already running for {job}")
    log = JOBS / job / "web" / f"{step}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    procs[(job, step)] = subprocess.Popen([str(c) for c in cmd], cwd=ROOT, env=ENV, stdout=log.open("w"),
                                         stderr=subprocess.STDOUT)


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def gpu_training():
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    return any("lerobot-train" in line or "train_job.py" in line for line in out.splitlines())


def videos():
    return sorted(p for p in VIDEOS.rglob("*.mp4") if not p.stem.endswith("_source"))


def thumb(src, out, at=0.4, width=480, crop_top=0):
    """One frame of `src` as a small PNG, made once."""
    if not out.exists():
        import imageio.v2 as imageio
        from PIL import Image
        frames = imageio.get_reader(src)
        n = frames.count_frames()
        im = Image.fromarray(frames.get_data(int(at * max(1, n - 1))))
        im = im.crop((0, crop_top, im.width, im.height))
        im.thumbnail((width, width))
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out)
    return FileResponse(out, media_type="image/png")


@app.get("/api/videos")
def list_videos():
    return [{"name": p.stem, "has_card": (JOBS / p.stem / "card.json").exists(), "thumb": f"/api/videos/{p.stem}/thumb",
             "url": f"/files/data/{p.relative_to(ROOT / 'data')}"} for p in videos()]


@app.get("/api/videos/{name}/thumb")
def video_thumb(name: str):
    video = next((p for p in videos() if p.stem == name), None)
    if video is None:
        raise HTTPException(404)
    return thumb(video, THUMBS / f"video_{name}.png")


@app.get("/api/robots/{name}/thumb")
def robot_thumb(name: str):
    clip = ROOT / "outputs" / "matrix" / f"cube_to_bowl__{name}.mp4"
    if not clip.exists():
        raise HTTPException(404)
    return thumb(clip, THUMBS / f"robot_{name}.png", at=0.35, crop_top=34)  # the clip's label line is burnt in


@app.post("/api/upload")
async def upload(file: UploadFile):
    """Saves the video as an mp4 of at most 15 s, 1280 px wide, no sound (what the card stage expects)."""
    stem = re.sub(r"[^a-z0-9_]+", "_", Path(file.filename or "video").stem.lower()).strip("_")[:40] or "video"
    if (VIDEOS / "uploads" / f"{stem}.mp4").exists() or (JOBS / stem).exists():
        stem = f"{stem}_{time.strftime('%H%M%S')}"
    raw = VIDEOS / "uploads" / f"{stem}_source{Path(file.filename or '.mp4').suffix.lower() or '.mp4'}"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(await file.read())
    import imageio_ffmpeg
    out = VIDEOS / "uploads" / f"{stem}.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-i", str(raw), "-t", str(MAX_SECONDS),
           "-vf", "scale='min(1280,iw)':-2", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    if subprocess.run(cmd).returncode or not out.exists():
        raise HTTPException(400, "could not read this video")
    return {"name": stem, "path": str(out.relative_to(ROOT))}


class Learn(BaseModel):
    video: str
    again: bool = False


@app.post("/api/jobs")
def make_card(req: Learn):
    video = next((p for p in videos() if p.stem == req.video), None)
    if video is None:
        raise HTTPException(404, f"no video {req.video}")
    job = video.stem
    if (JOBS / job / "card.json").exists() and not req.again:
        if not (JOBS / job / "check.json").exists():
            start(job, "check", [PY, "-m", "web.worker", "check", job])
        return {"job": job, "reused": True}
    start(job, "learn", [PY, "-m", "web.worker", "learn", video])
    return {"job": job, "reused": False}


@app.post("/api/jobs/{job}/check")
def check(job: str):
    if not (JOBS / job / "card.json").exists():
        raise HTTPException(404, "no card yet")
    start(job, "check", [PY, "-m", "web.worker", "check", job])
    return {"ok": True}


class Run(BaseModel):
    robots: list[str]
    trials: int = 5


@app.post("/api/jobs/{job}/run")
def run(job: str, req: Run):
    if not req.robots:
        raise HTTPException(400, "pick at least one robot")
    start(job, "try", [PY, "-m", "web.worker", "try", job, "--robots", *req.robots, "--trials", max(1, min(req.trials, 20))])
    return {"ok": True}


class Train(BaseModel):
    robots: list[str]


@app.post("/api/jobs/{job}/train")
def train(job: str, req: Train):
    card = read(JOBS / job / "card.json")
    if not card:
        raise HTTPException(404, "no card yet")
    if card.get("kind", "pick_place") != "pick_place":
        raise HTTPException(400, "training is for pick-and-place skills only so far")
    if gpu_training():
        raise HTTPException(409, "the GPU is busy with another training; try again when it is done")
    start(job, "train", [PY, ROOT / "scripts" / "train_job.py", JOBS / job, "--robots", *req.robots])
    return {"ok": True}


def train_status(card_name):
    folder = TRAIN / card_name
    report = read(folder / "report.json", {})
    robots = {}
    for robot, info in report.get("robots", {}).items():
        row = dict(info)
        log = folder / f"train_{robot}.log"
        if "train" not in row and log.exists():
            steps = re.findall(r"step:(\d+(?:\.\d+)?)K", log.read_text(errors="ignore")[-20000:])
            row["train"] = {"running": True, "step_k": float(steps[-1]) if steps else 0.0}
        if "train" in row and "eval" not in row and (folder / f"eval_{robot}.log").exists():
            row["eval"] = {"running": True}
        robots[robot] = row
    return {"steps": report.get("steps"), "trials": report.get("trials"), "robots": robots,
            "minutes_total": report.get("minutes_total")}


def video_url(path):
    if not path:
        return None
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    return f"/files/data/{p.relative_to(ROOT / 'data')}" if p.is_relative_to(ROOT / "data") else None


@app.get("/api/jobs/{job}")
def job_state(job: str):
    out = JOBS / job
    if not out.exists():
        raise HTTPException(404, f"no job {job}")
    web = out / "web"
    report = read(out / "report.json", {})
    card = read(out / "card.json")
    muse = read(out / "card_muse.json")
    steps = {s.stem: read(s, {}) for s in web.glob("*.json")} if web.exists() else {}
    for step in ("learn", "check", "try", "train"):
        if step in steps:
            steps[step]["alive"] = running(job, step)
    runs = {k[4:]: v for k, v in steps.items() if k.startswith("run_")}
    for v in runs.values():
        if v.get("clip"):
            v["clip_url"] = f"/files/jobs/{job}/{v['clip']}?t={int(v.get('updated', 0))}"
    return {
        "job": job,
        "video_url": video_url(report.get("video")),
        "stages": [s for s in report.get("stages", []) if s["stage"].startswith(("Muse", "SAM", "events"))],
        "overlay_url": f"/files/jobs/{job}/tracks_overlay.mp4" if (out / "tracks_overlay.mp4").exists() else None,
        "card": card,
        "evidence": (muse or {}).get("evidence"),
        "check": read(out / "check.json"),
        "steps": steps,
        "runs": runs,
        "training": train_status(card["name"]) if card else None,
        "gpu_busy": gpu_training(),
    }


@app.get("/api/robots")
def robots():
    from translator.robots import ROBOTS
    rows = []
    for name, r in ROBOTS.items():
        if name.endswith("_muse"):
            continue
        tool = Path(r.tool[1]).stem if r.tool else None
        gripper = {"2f85": "Robotiq 2F-85"}.get(tool, tool) if tool else "its own"
        rows.append({"name": name, "written_by": "Muse" if "/muse/" in r.source else "by hand", "gripper": gripper,
                     "thumb": f"/api/robots/{name}/thumb",
                     "hands": r.hands, "moves": r.mobile, "payload_kg": r.payload_kg, "model": r.xml.parent.name,
                     "notes": r.notes})
    return rows


@app.get("/files/{path:path}")
def files(path: str):
    """Videos and images from outputs/ and data/videos/ only."""
    base = {"jobs": ROOT / "outputs" / "jobs", "data": ROOT / "data"}.get(path.split("/", 1)[0])
    if base is None:
        raise HTTPException(404)
    target = (base / path.split("/", 1)[1]).resolve() if "/" in path else None
    if target is None or not target.is_relative_to(base.resolve()) or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


app.mount("/", StaticFiles(directory=ROOT / "web" / "static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
