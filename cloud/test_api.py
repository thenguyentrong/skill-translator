"""The upload rules, without Modal: .venv/bin/python cloud/test_api.py"""
import json
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


def fresh(tmp=None):
    tmp = tmp or Path(tempfile.mkdtemp())
    store, started, tried = {}, [], []
    client = TestClient(A.make_api(store, tmp, started.append, lambda *a: tried.append(a), live_url="wss://x"), raise_server_exceptions=False)
    return client, store, tmp, started, tried


def ready(store, job, check):
    store[f"job:{job}"] = {"created": time.time(), "state": "ready", "stages": [], "check": check, "overlay": "tracks_overlay.mp4"}


def spent(tmp, who="modal"):
    return json.loads((tmp / "budget.json").read_text())[who]


def test_upload():
    c, store, tmp, started, _ = fresh()
    r = c.post("/jobs", content=b"video")
    assert r.status_code == 200
    job = r.json()["job"]
    assert started == [job] and (tmp / job / "upload").read_bytes() == b"video"
    assert c.get(f"/jobs/{job}").json()["state"] == "queued"
    assert c.post("/jobs", content=b"").status_code == 400
    A.MAX_BYTES, keep = 10, A.MAX_BYTES
    assert c.post("/jobs", content=b"x" * 11).status_code == 413
    A.MAX_BYTES = keep
    assert len([p for p in tmp.iterdir() if p.is_dir()]) == 1, "a refused upload leaves nothing behind"
    assert spent(tmp, "meta") == A.VIDEO_USD["meta"], "only real jobs count"


def test_budget_stops_for_good():
    keep = dict(A.BUDGET_USD), A.VIDEOS_PER_HOUR
    A.BUDGET_USD.update(meta=0.70, modal=0.30)
    A.VIDEOS_PER_HOUR = 100
    c, store, tmp, started, tried = fresh()
    assert c.post("/jobs", content=b"x").status_code == 200
    job = next(k[4:] for k in store)
    ready(store, job, {"a": "can try", "b": "can try", "c": "can try"})
    assert c.post(f"/jobs/{job}/run", json={"robots": ["a", "b"]}).status_code == 403, "Modal over budget"
    assert not tried and not store.get(f"run:{job}:a")
    assert c.post("/jobs", content=b"x").status_code == 200, "Meta reaches 0.70 exactly"
    assert c.post(f"/jobs/{job}/run", json={"robots": ["a"]}).status_code == 200, "Modal reaches 0.30 exactly"
    r = c.post("/jobs", content=b"x")
    assert r.status_code == 403 and len(started) == 2
    assert spent(tmp) == 0.30 and spent(tmp, "meta") == 0.70
    assert c.post(f"/jobs/{job}/run", json={"robots": ["b"]}).status_code == 403
    c2, *_, started2, _ = fresh(tmp)
    assert c2.post("/jobs", content=b"x").status_code == 403, "a new container is still closed"
    assert not started2
    (tmp / "budget.json").write_text("broken")
    assert c2.post("/jobs", content=b"x").status_code == 403, "an unreadable budget stays closed"
    A.BUDGET_USD.update(keep[0])
    A.VIDEOS_PER_HOUR = keep[1]


def test_one_address_cannot_drain_it():
    c, *_ = fresh()
    for _ in range(A.VIDEOS_PER_HOUR):
        assert c.post("/jobs", content=b"x").status_code == 200
    assert c.post("/jobs", content=b"x").status_code == 429
    assert c.post("/jobs", content=b"x", headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "1.2.3.4"}).status_code == 429, "faked address"


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
    assert c.post(url, json={"robots": ["a"]}).status_code == 409
    store[f"job:{job}"]["state"] = "ready"
    assert c.post(url, json={"robots": []}).status_code == 400
    assert c.post(url, json={"robots": ["e"]}).status_code == 400, "a robot that said no"
    assert c.post(url, json={"robots": ["../x"]}).status_code == 400
    assert c.post(url, json={"robots": ["a", "b", "c", "d"]}).status_code == 400, "over 3"
    assert c.post(url, json={"robots": ["a", "b"]}).json() == {"started": ["a", "b"]}
    assert c.post(url, json={"robots": ["a"]}).json() == {"started": []}, "not charged twice"
    assert spent(tmp) == 2 * A.RUN_USD["modal"]
    assert c.post(url, json={"robots": ["c", "d"]}).status_code == 400, "3 per video in total"
    assert len(tried) == 2
    assert c.get(f"/jobs/{job}").json()["runs"]["a"]["state"] == "waiting"


def test_live():
    c, store, tmp, *_ = fresh()
    job = "f" * 32
    ready(store, job, {"g1": "can try", "lite6": "too big: no"})
    url = f"/jobs/{job}/live"
    assert c.post(url, json={"robot": "g1"}).status_code == 409, "it has not run yet"
    store[f"run:{job}:g1"] = {"state": "running", "queued": time.time()}
    assert c.post(url, json={"robot": "g1"}).status_code == 409
    store[f"run:{job}:g1"]["state"] = "done"
    store[f"run:{job}:lite6"] = {"state": "done", "queued": time.time()}
    assert c.post(url, json={"robot": "lite6"}).status_code == 409, "a robot that said no"
    for i in range(A.LIVE_PER_HOUR):
        r = c.post(url, json={"robot": "g1"})
        assert r.status_code == 200 and r.json()["url"].startswith("wss://x/live/")
    assert c.post(url, json={"robot": "g1"}).status_code == 429
    assert spent(tmp) == round(A.LIVE_PER_HOUR * A.LIVE_USD["modal"], 4), "each session is paid for up front"
    tickets = [v for k, v in store.items() if k.startswith("live:")]
    assert len(tickets) == A.LIVE_PER_HOUR and tickets[0]["robot"] == "g1"


def test_files():
    c, store, tmp, *_ = fresh()
    job = "c" * 32
    ready(store, job, {"ur5e": "can try"})
    (tmp / job).mkdir()
    for n in ("tracks_overlay.mp4", "clip.mp4", "upload", "ur5e_run.json", "secret.json"):
        (tmp / job / n).write_bytes(b"data")
    store[f"run:{job}:ur5e"] = {"state": "done", "queued": time.time(), "log": "ur5e_run.json"}
    assert c.get(f"/jobs/{job}").json()["runs"]["ur5e"]["log_url"].endswith("ur5e_run.json")
    assert c.get(f"/jobs/{job}/files/ur5e_run.json").status_code == 200
    assert c.get(f"/jobs/{job}/files/secret.json").status_code == 404, "only files the job lists"
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
    (tmp / "budget.json").write_text('{"meta": 1, "modal": 1}')
    A.sweep(store, tmp, now=100001)
    assert sorted(store) == [f"job:{new}", f"run:{new}:ur5e"]
    assert sorted(p.name for p in tmp.iterdir()) == [new, "budget.json"], "the budget is never swept"


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
