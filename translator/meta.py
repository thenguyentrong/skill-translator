"""Meta Model API: SAM 3.1 tracking and Muse Spark calls. Keys come from .env and are never printed."""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.meta.ai/v1"
SAM_PRICE_PER_FRAME = 0.20 / 1000
SAM_MIN_FRAMES = 50

_BOX = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>")
_FRAME = re.compile(r"^\s*<(\d+)f>")


def api_key(name="MODEL_API_KEY"):
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(name + "="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value
    raise RuntimeError(f"{name} is not set (put it in {env})")


def data_url(path, mime="video/mp4"):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def stream_response(body, key=None):
    """POST /responses with stream=true. Returns (list of output_text deltas, usage dict)."""
    body = dict(body, stream=True)
    req = urllib.request.Request(API + "/responses", data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key or api_key()}", "Content-Type": "application/json",
        "Accept": "text/event-stream"})
    deltas, usage = [], None
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                event = json.loads(data)
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    deltas.append(event.get("delta", ""))
                elif kind == "response.completed":
                    usage = event.get("response", {}).get("usage")
                elif kind in ("response.failed", "error"):
                    raise RuntimeError(f"API error: {json.dumps(event)[:400]}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:400]}") from None
    return deltas, usage


def parse_sam(deltas):
    """SAM wire lines -> {frame: {object_id: (x1, y1, x2, y2, confidence or None)}}, plus (w, h)."""
    frames, size = {}, None
    for chunk in "".join(deltas).splitlines() if len(deltas) == 1 else deltas:
        m = _FRAME.match(chunk)
        if not m:
            continue
        boxes = {}
        for oid, x1, y1, x2, y2, w, h, c in _BOX.findall(chunk):
            boxes[int(oid)] = (int(x1), int(y1), int(x2), int(y2), float(c) if c else None)
            size = (int(w), int(h))
        frames[int(m.group(1))] = boxes
    return frames, size


def sam_track(video_path, prompt, confidence=True):
    """Track every instance of `prompt` (one short noun phrase) through the video."""
    body = {"model": "sam-3.1", "input": [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_video", "video_url": data_url(video_path)}]}]}
    if confidence:
        body["metadata"] = {"include_confidence": "true"}
    deltas, usage = stream_response(body)
    frames, size = parse_sam(deltas)
    billed = (usage or {}).get("video_frames_processed")
    cost = max(billed or 0, SAM_MIN_FRAMES) * SAM_PRICE_PER_FRAME if billed is not None else None
    return {"prompt": prompt, "size": size, "frames": frames, "usage": usage, "cost_usd": cost}
