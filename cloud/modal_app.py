"""Translator in the cloud: `bash cloud/deploy.sh` (see cloud/README.md).

web: the API and the budget, no MuJoCo, no Meta key. ingest: ffmpeg on the uploaded file, no secrets at all.
learn: SAM + Muse + every robot's yes or no. robot_try: one robot, simulation only.
"""
import traceback
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
UNUSED = ["**/.git", "**/.git/**", "**/__pycache__/**"] + [f"mujoco_menagerie/{r}/**" for r in (
    "booster_t1", "kinova_gen3", "pal_talos", "rainbow_robotics_rby1", "rethink_robotics_sawyer", "universal_robots_ur10e")]

app = modal.App("translator")
store = modal.Dict.from_name("translator-state", create_if_missing=True)
files = modal.Volume.from_name("translator-jobs", create_if_missing=True)
JOBS = Path("/jobs")

web_image = (modal.Image.debian_slim(python_version="3.12")
             .pip_install("fastapi==0.162.0")
             .env({"PYTHONPATH": "/app"})
             .add_local_dir(ROOT / "cloud", "/app/cloud", ignore=["**/__pycache__/**"]))
worker_image = (modal.Image.debian_slim(python_version="3.12")
                .apt_install("ffmpeg", "libosmesa6", "libgl1", "libglib2.0-0", "fonts-dejavu-core")
                .pip_install("mujoco==3.17.0", "mink==1.3.0", "daqp==0.10.3", "numpy==2.2.6", "imageio==2.38.1",
                             "imageio-ffmpeg==0.6.0", "pillow==12.3.0")
                .env({"MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa", "PYTHONPATH": "/app:/app/scripts", "PRACTICE_WORKERS": "8"})
                .add_local_dir(ROOT / "cloud", "/app/cloud", ignore=["**/__pycache__/**"])
                .add_local_dir(ROOT / "translator", "/app/translator", ignore=["**/__pycache__/**"])
                .add_local_dir(ROOT / "scripts", "/app/scripts", ignore=["**/__pycache__/**"])
                .add_local_dir(ROOT / "robots", "/app/robots")
                .add_local_dir(ROOT / "cards", "/app/cards")
                .add_local_dir(ROOT / "assets/robots", "/app/assets/robots", ignore=UNUSED))


def update(job, **fields):
    key = f"job:{job}"
    store[key] = {**store[key], **fields}


@app.function(image=worker_image, volumes={"/jobs": files}, cpu=2, memory=2048, timeout=240, max_containers=4)
def ingest(job):
    from cloud.jobs import SORRY, NotUsable, prepare
    files.reload()
    folder = JOBS / job
    try:
        prepare(folder / "upload", folder / "clip.mp4")
    except NotUsable as e:
        return update(job, state="failed", error=str(e))
    except Exception:
        traceback.print_exc()
        return update(job, state="failed", error=SORRY)
    finally:
        (folder / "upload").unlink(missing_ok=True)
        files.commit()
    learn.spawn(job)


@app.function(image=worker_image, volumes={"/jobs": files}, secrets=[modal.Secret.from_name("translator-meta")],
              cpu=2, memory=4096, timeout=720, max_containers=2)
def learn(job):
    from cloud.jobs import SORRY, NotUsable, make_card
    files.reload()
    folder = JOBS / job

    def save(**fields):
        if "overlay" in fields:
            files.commit()
        update(job, **fields)

    try:
        make_card(folder / "clip.mp4", folder, save)
    except NotUsable as e:
        update(job, state="failed", error=str(e))
    except Exception:
        traceback.print_exc()
        update(job, state="failed", error=SORRY)
    finally:
        (folder / "clip.mp4").unlink(missing_ok=True)
        files.commit()


@app.function(image=worker_image, volumes={"/jobs": files}, cpu=8, memory=12288, timeout=1500, max_containers=3)
def robot_try(job, robot, trials):
    from cloud.jobs import try_one
    key = f"run:{job}:{robot}"
    run = store[key]
    store[key] = {**run, "state": "running"}
    files.reload()
    try:
        done = try_one(store[f"job:{job}"]["card"], robot, JOBS / job, trials)
        files.commit()
        store[key] = {**run, "state": "done", **done}
    except Exception:
        traceback.print_exc()
        store[key] = {**run, "state": "failed", "error": "This robot's try crashed."}


@app.function(image=web_image, volumes={"/jobs": files}, schedule=modal.Period(hours=6))
def clean():
    from cloud.api import sweep
    files.reload()
    sweep(store, JOBS)
    files.commit()


@app.function(image=web_image, volumes={"/jobs": files}, max_containers=1, timeout=300)  # one container: one budget lock
@modal.concurrent(max_inputs=32)
@modal.asgi_app(label="translator-api")
def web():
    from cloud.api import make_api
    return make_api(store, JOBS, ingest.spawn, robot_try.spawn, files.commit, files.reload)
