"""Step 2: from SAM tracks to task events (which object moved, grab, release, where it ended)."""
import numpy as np


def _centre(b):
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def _series(track, oid):
    frames = sorted(f for f, boxes in track["frames"].items() if oid in boxes)
    return frames, {f: track["frames"][f][oid] for f in frames}


def _overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def find_events(obj_track, container_track, hand_track, fps, n_frames):
    """Pick the object that moves the most, then read the grab, the carry and the release from its path."""
    width = obj_track["size"][0]
    ids = {oid for boxes in obj_track["frames"].values() for oid in boxes}
    paths = {}
    for oid in ids:
        frames, boxes = _series(obj_track, oid)
        centres = np.array([_centre(boxes[f]) for f in frames])
        paths[oid] = (frames, boxes, centres, float(np.max(np.linalg.norm(centres - centres[0], axis=1))))
    moved = max(paths, key=lambda o: paths[o][3])
    frames, boxes, centres, travel = paths[moved]
    if travel < 0.05 * width:
        return {"moved_object": None, "why": "no object moved more than 5 % of the frame width"}

    # speed in px/frame, smoothed over 3 samples
    gaps = np.diff(frames)
    speed = np.linalg.norm(np.diff(centres, axis=0), axis=1) / np.maximum(gaps, 1)
    speed = np.convolve(speed, np.ones(3) / 3, mode="same")
    moving = speed > 0.004 * width
    first = int(np.argmax(moving))
    last = len(moving) - 1 - int(np.argmax(moving[::-1]))
    grab_f, release_f = frames[first], frames[last + 1]

    hand_at_grab = any(_overlap(h, boxes[grab_f]) > 0 for h in hand_track["frames"].get(grab_f, {}).values())

    cont = [b for boxes_ in container_track["frames"].values() for b in boxes_.values()]
    cbox = np.median(np.array([b[:4] for b in cont]), axis=0) if cont else None
    end = centres[-1]
    inside = bool(cbox is not None and cbox[0] <= end[0] <= cbox[2] and cbox[1] <= end[1] <= cbox[3])

    ob = boxes[frames[0]]
    obj_w = ob[2] - ob[0]
    return {
        "moved_object": {"prompt": obj_track["prompt"], "id": int(moved), "travel_px": round(travel, 1)},
        "grab": {"frame": int(grab_f), "time_s": round(grab_f / fps, 2), "hand_touching": hand_at_grab},
        "release": {"frame": int(release_f), "time_s": round(release_f / fps, 2)},
        "last_seen": {"frame": int(frames[-1]), "time_s": round(frames[-1] / fps, 2),
                      "visible_until_end": frames[-1] >= n_frames - 2},
        "start_px": [round(float(v), 1) for v in centres[0]],
        "end_px": [round(float(v), 1) for v in end],
        "container": {"prompt": container_track["prompt"], "box_px": None if cbox is None else [round(float(v), 1) for v in cbox],
                      "seen_in_frames": len(container_track["frames"])},
        "ends_inside_container": inside,
        "size_ratio_object_to_container": None if cbox is None else round(obj_w / (cbox[2] - cbox[0]), 3),
        "other_objects_of_same_kind": len(ids) - 1,
    }


def timeline(ev):
    if not ev.get("moved_object"):
        return ev.get("why", "nothing moved")
    o, c = ev["moved_object"]["prompt"], ev["container"]["prompt"]
    lines = [
        f"{o} {ev['moved_object']['id']} is the one that moves ({ev['moved_object']['travel_px']} px); "
        f"{ev['other_objects_of_same_kind']} other {o}s stay put",
        f"grab at {ev['grab']['time_s']} s (frame {ev['grab']['frame']}), hand touching it: {ev['grab']['hand_touching']}",
        f"release at {ev['release']['time_s']} s (frame {ev['release']['frame']})",
        f"ends inside the {c}: {ev['ends_inside_container']}"
        + ("" if ev["last_seen"]["visible_until_end"] else f" (last seen at {ev['last_seen']['time_s']} s, then hidden)"),
        f"{o} width / {c} width = {ev['size_ratio_object_to_container']}",
    ]
    return "\n".join(lines)
