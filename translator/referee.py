"""Step 6: a referee that reads the robot's clip and says whether the task ended as the card says.

SAM 3.1 tracks the object and the container, events.py reads the path, and a rule on pixels decides. No simulator state
goes in. Muse Spark is asked only when the pixels do not settle it, and it gets the clip and a plain question, never
the pixel score. Works on pick-and-place cards; door and carry cards have no object-in-container test to read.
"""
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .card_writer import SPARK_IN, SPARK_OUT
from .events import find_events
from .meta import ROOT, data_url, sam_track, stream_response

OUT = ROOT / "outputs" / "referee"
MAX_FRAMES = 50  # SAM bills at least 50 frames a request, so a shorter clip saves nothing and a longer one costs more
BUDGET = 1.50

# How things look in the scene, not what the card calls them: the scene paints the held object red and the container
# green, so "lemon" finds nothing.
HELD = {"sphere": "red ball", "box": "red block", "cylinder": "red cylinder"}
HOLDER = {"bowl": "green bowl", "box": "green box", "plate": "green plate", "basket": "green plate"}
HOLDER_WORD = {"bowl": "bowl", "box": "box", "plate": "plate", "basket": "tray"}

# On the normalised distance from the container's centre: 1 is the edge of its box in the image.
PASS_BELOW, FAIL_ABOVE = 0.70, 1.15
STILL_PX = 0.012  # of the frame width, over the last frames


class OverBudget(RuntimeError):
    pass


class Spend:
    """Every paid call lands in one file, so the ceiling holds across runs and across scripts."""

    def __init__(self, path=OUT / "spend.jsonl", limit=BUDGET):
        self.path, self.limit = Path(path), limit

    @property
    def total(self):
        if not self.path.exists():
            return 0.0
        return sum(json.loads(line)["usd"] for line in self.path.read_text().splitlines() if line.strip())

    def check(self, estimate):
        if self.total + estimate > self.limit:
            raise OverBudget(f"spent ${self.total:.3f}, next call ~${estimate:.3f}, ceiling ${self.limit:.2f}")

    def add(self, what, usd):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"what": what, "usd": round(float(usd or 0), 5), "at": time.strftime("%H:%M:%S")}) + "\n")


def _shapes(card):
    """The held object's and the container's card entries, in the order the success test names them."""
    return card["objects"][card["success"]["object"]], card["objects"][card["success"]["container"]]


def prompts(card):
    held, holder = _shapes(card)
    flat = held["shape"] == "cylinder" and held["size"][2] < held["size"][0] / 2  # "red cylinder" finds no cookie
    return "red disc" if flat else HELD[held["shape"]], HOLDER[holder["shape"]]


def _tracks_file(cache, clip, prompt):
    return Path(cache) / f"{Path(clip).stem}__{prompt.replace(' ', '_')}.json"


def _load(path):
    t = json.loads(path.read_text())
    t["frames"] = {int(f): {int(o): tuple(b) for o, b in boxes.items()} for f, boxes in t["frames"].items()}
    return t


def track(clip, prompt, cache=None, spend=None):
    """SAM on one prompt, kept on disk: rules can change without paying for the same clip twice."""
    path = _tracks_file(cache, clip, prompt) if cache else None
    if path and path.exists():
        return _load(path)
    if spend:
        spend.check(0.011)
    t0 = time.time()
    t = sam_track(clip, prompt)
    t["seconds"] = round(time.time() - t0, 2)
    if spend:
        spend.add(f"sam {Path(clip).stem} {prompt}", t["cost_usd"] or MAX_FRAMES * 0.0002)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(t))
    return t


def single_path(t):
    """A robot clip has one held object, so every id SAM gives is that object: keep the surest box in each frame.
    A track that SAM drops and picks up again then stays one path instead of two short ones."""
    frames = {}
    for f, boxes in t["frames"].items():
        frames[f] = {1: max(boxes.values(), key=lambda b: b[4] or 0)} if boxes else {}
    return dict(t, frames=frames)


def _end_distance(end, box, square):
    """0 = centre of the container's image box, 1 = its edge (an ellipse for round things, the box for a square bin)."""
    a, b = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
    dx, dy = (end[0] - (box[0] + box[2]) / 2) / a, (end[1] - (box[1] + box[3]) / 2) / b
    return max(abs(dx), abs(dy)) if square else math.hypot(dx, dy)


def read_pixels(obj_track, cont_track, fps, card):
    """Tracks -> ("pass" | "fail" | None for a tie, why, details)."""
    n_frames = max(len(obj_track["frames"]), len(cont_track["frames"]))
    obj = single_path(obj_track)
    seen = sorted(f for f, b in obj["frames"].items() if b)
    if not seen:
        return None, "object never found", {}
    ev = find_events(obj, cont_track, {"frames": {}}, fps, n_frames)
    if not ev.get("moved_object"):
        return "fail", "object never moved", {"events": ev}
    box = ev["container"]["box_px"]
    if box is None:
        return None, "container never found", {"events": ev}
    held, holder = _shapes(card)
    dist = _end_distance(ev["end_px"], box, holder["shape"] == "box")
    width = obj["size"][0]
    tail = [f for f in seen if f >= seen[-1] - 4]
    centres = np.array([[(obj["frames"][f][1][0] + obj["frames"][f][1][2]) / 2,
                         (obj["frames"][f][1][1] + obj["frames"][f][1][3]) / 2] for f in tail])
    drift = float(np.linalg.norm(centres.max(axis=0) - centres.min(axis=0))) / width
    details = {"events": ev, "end_distance": round(dist, 3), "drift": round(drift, 4), "inside_box": ev["ends_inside_container"]}
    if not ev["last_seen"]["visible_until_end"]:
        return None, f"object last seen at {ev['last_seen']['time_s']} s", details
    if drift > STILL_PX:
        return None, "object still moving at the end", details
    if dist <= PASS_BELOW:
        return "pass", f"ends {dist:.2f} from the container's centre", details
    if dist >= FAIL_ABOVE:
        return "fail", f"ends {dist:.2f} from the container's centre, outside", details
    return None, f"too close to the edge to call ({dist:.2f})", details


BLIND_SCHEMA = {
    "type": "object",
    "properties": {
        "ends": {"type": "string", "enum": ["in_container", "not_in_container", "cannot_tell"]},
        "seen": {"type": "string", "description": "one sentence: where the object is in the last second"},
    },
    "required": ["ends", "seen"],
}


def blind_question(card):
    """The whole of what Muse is told. It carries the task and nothing the pixels found."""
    obj = prompts(card)[0]
    word = "green " + HOLDER_WORD[_shapes(card)[1]["shape"]]
    return (f"A robot arm tries to put a {obj} into a {word}. Watch to the very end of the video. In the last second, "
            f"is the {obj} resting in the {word}? Touching the rim from outside, lying beside it or lying behind it "
            "all count as not in it.")


def blind_muse(clip, card, spend=None):
    if spend:
        spend.check(0.02)
    body = {
        "model": "muse-spark-1.3",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": blind_question(card)},
            {"type": "input_video", "video_url": data_url(clip)}]}],
        "text": {"format": {"type": "json_schema", "name": "where_it_ended", "schema": BLIND_SCHEMA}},
        "reasoning": {"effort": "low"},
        "max_output_tokens": 3000,
    }
    t0 = time.time()
    deltas, usage = stream_response(body)
    cost = (usage.get("input_tokens", 0) * SPARK_IN + usage.get("output_tokens", 0) * SPARK_OUT) if usage else 0.0
    if spend:
        spend.add(f"muse {Path(clip).stem}", cost)
    return dict(json.loads("".join(deltas)), seconds=round(time.time() - t0, 2), cost_usd=round(cost, 5))


def referee(clip, card, fps, cache=None, spend=None, muse_cache=None):
    """One clip and its card -> a verdict. Reads the mp4 and the card, nothing else."""
    held, holder = prompts(card)
    with ThreadPoolExecutor(2) as pool:
        obj, cont = pool.map(lambda p: track(clip, p, cache, spend), (held, holder))
    verdict, why, details = read_pixels(obj, cont, fps, card)
    out = {"clip": Path(clip).name, "held_prompt": held, "container_prompt": holder, "decided_by": "sam", "pixels": verdict,
           "why": why, "seconds": max(obj.get("seconds", 0), cont.get("seconds", 0)),
           "cost_usd": (obj.get("cost_usd") or 0) + (cont.get("cost_usd") or 0), **details}
    if verdict is None:
        cached = Path(muse_cache) / (Path(clip).stem + ".json") if muse_cache else None
        if cached and cached.exists():
            m = json.loads(cached.read_text())
        else:
            m = blind_muse(clip, card, spend)
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps(m))
        out["muse"] = m
        out["decided_by"] = "muse"
        out["seconds"] += m.get("seconds", 0)
        out["cost_usd"] += m.get("cost_usd", 0)
        verdict = {"in_container": "pass", "not_in_container": "fail"}.get(m["ends"])
    out["verdict"] = verdict or "unsure"
    return out
