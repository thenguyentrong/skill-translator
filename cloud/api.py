"""The public API behind the site's upload panel: one video -> a skill card -> up to 3 robots try it.

Storage and the workers are passed in, so these rules can be tested without Modal (cloud/test_api.py).
A job id is a random 128-bit value. Reading a job needs the id, starting anything also needs the access code.
"""
import hmac
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

MAX_BYTES = 60 * 1024 * 1024
MAX_ROBOTS = 3
TRIALS = 5
JOBS_PER_DAY = 15  # a 15 s clip costs at most about $0.35 in Meta API calls
RUNS_PER_DAY = 60
WRONG_CODES_PER_HOUR = 10
KEEP_SECONDS = 24 * 3600
JOB_TIMEOUT = 15 * 60
RUN_TIMEOUT = 30 * 60
ORIGINS = ["https://thenguyentrong.github.io", "http://127.0.0.1:8123"]
FIELDS = ("state", "error", "stages", "card", "evidence", "check", "created")
ID = re.compile(r"[0-9a-f]{32}")
CLIP = re.compile(r"[a-z0-9_]+\.mp4")


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
        elif key.startswith("day:") and key[4:14] < time.strftime("%Y-%m-%d", time.gmtime(now - 2 * 86400)):
            store.pop(key)
    for folder in root.iterdir() if root.exists() else ():
        if folder.is_dir() and folder.name not in live and ID.fullmatch(folder.name):
            shutil.rmtree(folder, ignore_errors=True)


def make_api(store, root, code, ingest, run_robot, commit=lambda: None, reload=lambda: None):
    app = FastAPI(title="Translator", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["X-Access-Code", "Content-Type"])
    root = Path(root)
    lock = threading.Lock()
    wrong = {}

    def guard(request, given):
        if not code:
            raise HTTPException(503, "uploads are switched off")
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
        now = time.time()
        with lock:
            if len(wrong) > 10000:
                wrong.clear()
            recent = wrong[ip] = [t for t in wrong.get(ip, []) if now - t < 3600]
            if len(recent) >= WRONG_CODES_PER_HOUR:
                raise HTTPException(429, "too many wrong codes, try again in an hour")
            if not hmac.compare_digest(given.encode(), code.encode()):
                recent.append(now)
                raise HTTPException(401, "wrong access code")

    def day_key(kind):
        return f"day:{time.strftime('%Y-%m-%d', time.gmtime())}:{kind}"

    def room(kind, limit, n=1):
        if store.get(day_key(kind), 0) + n > limit:
            raise HTTPException(429, f"today's limit of {limit} {kind} is used up, try again tomorrow")

    def take(kind, limit, n=1):
        with lock:
            room(kind, limit, n)
            store[day_key(kind)] = store.get(day_key(kind), 0) + n

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

    def save_upload(job):
        take("jobs", JOBS_PER_DAY)
        store[f"job:{job}"] = {"created": time.time(), "state": "queued", "stages": []}
        commit()
        ingest(job)

    @app.post("/jobs")
    async def create(request: Request, x_access_code: str = Header("")):
        await run_in_threadpool(guard, request, x_access_code)
        await run_in_threadpool(room, "jobs", JOBS_PER_DAY)
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
            await run_in_threadpool(save_upload, job)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return {"job": job}

    @app.get("/jobs/{job}")
    def read(job: str):
        return view(job, load(job))

    @app.post("/jobs/{job}/run")
    def run(job: str, req: Run, request: Request, x_access_code: str = Header("")):
        guard(request, x_access_code)
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
        take("robot runs", RUNS_PER_DAY, len(fresh))
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
