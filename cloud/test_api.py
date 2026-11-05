"""The upload rules, without Modal: .venv/bin/python cloud/test_api.py"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from cloud import api as A
from cloud import jobs as J

CODE = "right-code"
HEAD = {"X-Access-Code": CODE}


def fresh(code=CODE):
    tmp = Path(tempfile.mkdtemp())
    store, started, tried = {}, [], []
    client = TestClient(A.make_api(store, tmp, code, started.append, lambda *a: tried.append(a)), raise_server_exceptions=False)
    return client, store, tmp, started, tried


def ready(store, job, check):
    store[f"job:{job}"] = {"created": time.time(), "state": "ready", "stages": [], "check": check, "overlay": "tracks_overlay.mp4"}


def test_code():
    c, store, tmp, started, _ = fresh()
    assert c.post("/jobs", content=b"x").status_code == 401
    assert c.post("/jobs", content=b"x", headers={"X-Access-Code": "nope"}).status_code == 401
    assert not started and not list(tmp.iterdir())
    for _ in range(8):
        c.post("/jobs", content=b"x", headers={"X-Access-Code": "nope"})
    assert c.post("/jobs", content=b"x", headers=HEAD).status_code == 429, "too many wrong codes"
    c2, *_ = fresh(code="")
    assert c2.post("/jobs", content=b"x", headers={"X-Access-Code": ""}).status_code == 503, "no code set = closed"


def test_upload():
    c, store, tmp, started, _ = fresh()
    r = c.post("/jobs", content=b"video", headers=HEAD)
    assert r.status_code == 200
    job = r.json()["job"]
    assert started == [job] and (tmp / job / "upload").read_bytes() == b"video"
    assert c.get(f"/jobs/{job}").json()["state"] == "queued"
    assert c.post("/jobs", content=b"", headers=HEAD).status_code == 400
    A.MAX_BYTES, keep = 10, A.MAX_BYTES
    assert c.post("/jobs", content=b"x" * 11, headers=HEAD).status_code == 413
    A.MAX_BYTES = keep
    assert len(list(tmp.iterdir())) == 1, "a refused upload leaves nothing behind"
    assert sum(v for k, v in store.items() if k.startswith("day:")) == 1, "only real jobs count"


def test_daily_limit():
    c, *_ = fresh()
    for _ in range(A.JOBS_PER_DAY):
        assert c.post("/jobs", content=b"x", headers=HEAD).status_code == 200
    assert c.post("/jobs", content=b"x", headers=HEAD).status_code == 429


def test_read():
    c, store, tmp, *_ = fresh()
    job = "a" * 32
    assert c.get(f"/jobs/{job}").status_code == 404
    assert c.get("/jobs/..%2f..%2fetc").status_code == 404
    ready(store, job, {"ur5e": "can try"})
    store[f"job:{job}"]["secret"] = "x"
    assert "secret" not in c.get(f"/jobs/{job}").json()
    store[f"job:{job}"].update(state="reading", created=time.time() - A.JOB_TIMEOUT - 1)
    assert c.get(f"/jobs/{job}").json()["state"] == "failed", "a stuck job ends"


def test_run():
    c, store, tmp, _, tried = fresh()
    job = "b" * 32
    check = {r: "can try" for r in "abcd"} | {"e": "too big: no"}
    store[f"job:{job}"] = {"created": time.time(), "state": "reading", "check": check}
    url = f"/jobs/{job}/run"
    assert c.post(url, json={"robots": ["a"]}, headers=HEAD).status_code == 409
    store[f"job:{job}"]["state"] = "ready"
    assert c.post(url, json={"robots": ["a"]}).status_code == 401
    assert c.post(url, json={"robots": []}, headers=HEAD).status_code == 400
    assert c.post(url, json={"robots": ["e"]}, headers=HEAD).status_code == 400, "a robot that said no"
    assert c.post(url, json={"robots": ["../x"]}, headers=HEAD).status_code == 400
    assert c.post(url, json={"robots": ["a", "b", "c", "d"]}, headers=HEAD).status_code == 400, "over 3"
    assert c.post(url, json={"robots": ["a", "b"]}, headers=HEAD).json() == {"started": ["a", "b"]}
    assert c.post(url, json={"robots": ["a"]}, headers=HEAD).json() == {"started": []}, "not charged twice"
    assert c.post(url, json={"robots": ["c", "d"]}, headers=HEAD).status_code == 400, "3 per video in total"
    assert len(tried) == 2
    assert c.get(f"/jobs/{job}").json()["runs"]["a"]["state"] == "waiting"


def test_files():
    c, store, tmp, *_ = fresh()
    job = "c" * 32
    ready(store, job, {"ur5e": "can try"})
    (tmp / job).mkdir()
    for n in ("tracks_overlay.mp4", "clip.mp4", "upload"):
        (tmp / job / n).write_bytes(b"data")
    assert c.get(f"/jobs/{job}/files/tracks_overlay.mp4").status_code == 200
    assert c.get(f"/jobs/{job}/files/clip.mp4").status_code == 404, "only files the job lists"
    assert c.get(f"/jobs/{job}/files/upload").status_code == 404
    assert c.get(f"/jobs/{job}/files/..%2F..%2Fsecret.mp4").status_code == 404
    assert c.get(f"/jobs/{'d' * 32}/files/tracks_overlay.mp4").status_code == 404


def test_sweep():
    tmp = Path(tempfile.mkdtemp())
    old, new, lost = "1" * 32, "2" * 32, "3" * 32
    store = {f"job:{old}": {"created": 0}, f"job:{new}": {"created": 100000}, f"run:{old}:ur5e": {}, f"run:{new}:ur5e": {}}
    for j in (old, new, lost):
        (tmp / j).mkdir()
    A.sweep(store, tmp, now=100001)
    assert sorted(store) == [f"job:{new}", f"run:{new}:ur5e"]
    assert [p.name for p in tmp.iterdir()] == [new]


def test_prepare():
    tmp = Path(tempfile.mkdtemp())
    good = ROOT / "data/videos/lemon_into_bowl_1cycle.mp4"
    J.prepare(good, tmp / "out.mp4")
    assert (tmp / "out.mp4").stat().st_size > 1000
    long = tmp / "long.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=20", str(long)], check=True)
    J.prepare(long, tmp / "cut.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,duration", "-of", "csv=p=0", str(tmp / "cut.mp4")], capture_output=True, text=True).stdout
    w, h, d = probe.strip().split(",")
    assert int(h) == 1280 and int(w) <= 720 and float(d) <= 15.1, probe
    (tmp / "note.txt").write_text("not a video")
    (tmp / "list.m3u8").write_text("#EXTM3U\n#EXTINF:1,\nhttp://169.254.169.254/latest/meta-data\n#EXT-X-ENDLIST\n")
    (tmp / "concat.mp4").write_text("ffconcat version 1.0\nfile http://169.254.169.254/x\n")
    for bad in ("note.txt", "list.m3u8", "concat.mp4"):
        try:
            J.prepare(tmp / bad, tmp / "bad.mp4")
        except J.NotUsable:
            continue
        raise AssertionError(f"{bad} was accepted")
    assert not (tmp / "bad.mp4").exists()


if __name__ == "__main__":
    tests = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(len(tests), "passed")
