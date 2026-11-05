"""The public API behind the site's upload panel: one video -> a skill card -> up to 3 robots try it.

Open to anyone until the total budget is used up, then every new job is refused for good.
Storage and the workers are passed in, so these rules can be tested without Modal (cloud/test_api.py).
A job id is a random 128-bit value, so a job's results can only be read with its link.
"""
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

BUDGET_USD = {"meta": 140.0, "modal": 25.0}
VIDEO_USD = {"meta": 0.35, "modal": 0.05}  # worst case: a 15 s clip through SAM and Muse, plus its two Modal steps
RUN_USD = {"modal": 0.20}  # worst case: one robot on 8 CPUs until the 25 min timeout
MAX_BYTES = 60 * 1024 * 1024
MAX_ROBOTS = 3
TRIALS = 5
VIDEOS_PER_HOUR = 5  # per address, so one person cannot use up the whole budget in minutes
KEEP_SECONDS = 24 * 3600
JOB_TIMEOUT = 15 * 60
RUN_TIMEOUT = 30 * 60
ORIGINS = ["https://thenguyentrong.github.io", "http://127.0.0.1:8123"]
FIELDS = ("state", "error", "stages", "card", "evidence", "check", "created")
ID = re.compile(r"[0-9a-f]{32}")
CLIP = re.compile(r"[a-z0-9_]+\.mp4")


class Budget:
    """Worst-case money promised so far per service, in a file on the volume so it lasts as long as the deployment.
    Each promise is saved before its job starts. A file that cannot be read counts as used up."""

    def __init__(self, path, commit):
        self.path, self.commit, self.lock = Path(path), commit, threading.Lock()

    def spent(self):
        try:
            saved = json.loads(self.path.read_text())
            return {k: float(saved[k]) for k in BUDGET_USD}
        except FileNotFoundError:
            return dict.fromkeys(BUDGET_USD, 0.0)
        except (ValueError, KeyError, TypeError):
            return dict.fromkeys(BUDGET_USD, float("inf"))

    def check(self, cost, n=1):
        spent = self.spent()
        if any(spent[k] + n * usd > BUDGET_USD[k] + 1e-9 for k, usd in cost.items()):
            raise HTTPException(403, "this demo has used up its budget and is closed")

    def take(self, cost, n=1):
        with self.lock:
            self.check(cost, n)
            spent = self.spent()
            for k, usd in cost.items():
                spent[k] = round(spent[k] + n * usd, 4)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({**spent, "updated": time.time()}))
            os.replace(tmp, self.path)
            self.commit()


class Run(BaseModel):
    robots: list[str]


def sweep(store, root, now=None):
    """Removes everything about jobs older than a day, and folders no job owns."""
    now = time.time() if now is None else now
    root = Path(root)
    live = set()
    for key in list(store.keys()):
        if key.startswith("job:"):
            job = key[4:]
            if now - store[key]["created"] > KEEP_SECONDS:
                store.pop(key)
            else:
                live.add(job)
    for key in list(store.keys()):
        if key.startswith("run:") and key.split(":")[1] not in live:
            store.pop(key)
    for folder in root.iterdir() if root.exists() else ():
        if folder.is_dir() and folder.name not in live and ID.fullmatch(folder.name):
            shutil.rmtree(folder, ignore_errors=True)


def make_api(store, root, ingest, run_robot, commit=lambda: None, reload=lambda: None):
    app = FastAPI(title="Translator", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    budget = Budget(root / "budget.json", commit)
    lock = threading.Lock()
    recent = {}

    def address(request):
        return request.client.host if request.client else "?"  # Modal sets this; forwarded headers can be faked

    def videos_left(ip):
        now = time.time()
        with lock:
            if len(recent) > 10000:
                recent.clear()
            times = recent[ip] = [t for t in recent.get(ip, []) if now - t < 3600]
            if len(times) >= VIDEOS_PER_HOUR:
                raise HTTPException(429, f"{VIDEOS_PER_HOUR} videos an hour at most, try again later")

    def load(job):
        state = store.get(f"job:{job}") if ID.fullmatch(job) else None
        if state is None:
            raise HTTPException(404, "no such job")
        return state

    def runs_of(job, state):
        rows = {}
        for robot in state.get("check") or {}:
            run = store.get(f"run:{job}:{robot}")
            if run:
                rows[robot] = run
        return rows

    def view(job, state):
        now = time.time()
        out = {k: state.get(k) for k in FIELDS}
        if out["state"] not in ("ready", "failed") and now - state["created"] > JOB_TIMEOUT:
            out.update(state="failed", error="This took too long and was stopped.")
        runs = {}
        for robot, run in runs_of(job, state).items():
            run = dict(run)
            if run["state"] in ("waiting", "running") and now - run["queued"] > RUN_TIMEOUT:
                run.update(state="failed", error="This took too long and was stopped.")
            if run.get("clip"):
                run["clip_url"] = f"/jobs/{job}/files/{run['clip']}"
            runs[robot] = run
        out["runs"] = runs
        out["overlay_url"] = f"/jobs/{job}/files/{state['overlay']}" if state.get("overlay") else None
        return out

    def save_upload(job, ip):
        videos_left(ip)
        budget.take(VIDEO_USD)
        with lock:
            recent[ip].append(time.time())
        store[f"job:{job}"] = {"created": time.time(), "state": "queued", "stages": []}
        commit()
        ingest(job)

    @app.post("/jobs")
    async def create(request: Request):
        ip = address(request)
        await run_in_threadpool(videos_left, ip)
        await run_in_threadpool(budget.check, VIDEO_USD)
        job = uuid.uuid4().hex
        folder = root / job
        folder.mkdir(parents=True)
        size = 0
        try:
            with (folder / "upload").open("wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "the video is over 60 MB")
                    f.write(chunk)
            if not size:
                raise HTTPException(400, "no video in the request")
            await run_in_threadpool(save_upload, job, ip)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return {"job": job}

    @app.get("/jobs/{job}")
    def read(job: str):
        return view(job, load(job))

    @app.post("/jobs/{job}/run")
    def run(job: str, req: Run):
        state = load(job)
        if state["state"] != "ready":
            raise HTTPException(409, "the robots have not answered yet")
        picked = list(dict.fromkeys(req.robots))
        if not picked:
            raise HTTPException(400, "pick at least one robot")
        bad = [r for r in picked if state["check"].get(r) != "can try"]
        if bad:
            raise HTTPException(400, f"cannot try this job: {', '.join(bad)}")
        started = runs_of(job, state)
        fresh = [r for r in picked if r not in started]
        if len(started) + len(fresh) > MAX_ROBOTS:
            raise HTTPException(400, f"at most {MAX_ROBOTS} robots per video")
        if not fresh:
            return {"started": []}
        budget.take(RUN_USD, len(fresh))
        for robot in fresh:
            store[f"run:{job}:{robot}"] = {"state": "waiting", "queued": time.time(), "trials": TRIALS}
            run_robot(job, robot, TRIALS)
        return {"started": fresh}

    @app.get("/jobs/{job}/files/{name}")
    def file(job: str, name: str):
        state = load(job)
        names = {state.get("overlay")} | {r.get("clip") for r in runs_of(job, state).values()}
        if not CLIP.fullmatch(name) or name not in names:
            raise HTTPException(404, "no such file")
        path = root / job / name
        if not path.is_file():
            try:
                reload()
            except Exception:  # another request has a file open; the next try gets it
                pass
        if not path.is_file():
            raise HTTPException(404, "no such file")
        return FileResponse(path, media_type="video/mp4")

    return app
