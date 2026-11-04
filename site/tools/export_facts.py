"""Facts each robot answers from, measured from its model: site/public/data/facts.json + example jobs from saved cards."""
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from translator.robots import ROBOTS
from translator.scene import DENSITY, build, sample_layout

NAMES = {"so101": "SO-101", "panda": "Franka Panda", "ur5e": "UR5e", "g1": "Unitree G1", "xarm7": "xArm7", "lite6": "Lite6",
         "tienkung3": "TienKung 3", "oli": "LimX Oli", "fr3": "Franka FR3"}
ORDER = ["ur5e", "fr3", "panda", "xarm7", "lite6", "so101", "g1", "tienkung3", "oli"]


def finger_gap(s, ctrl, steps=400):
    """Closest distance (m) between the two finger sides with the gripper at `ctrl`, from the collision shapes."""
    sides = s._gripper_sides()
    if not sides or not sides[0] or not sides[1]:
        return None
    m = s.model
    d = mujoco.MjData(m)
    mujoco.mj_copyData(d, m, s.data)
    d.ctrl[s.gripper_ids[0]] = ctrl
    for _ in range(steps):
        mujoco.mj_step(m, d)
    return float(min(mujoco.mj_geomDistance(m, d, a, b, 0.5, None) for a in sides[0] for b in sides[1]))


def tips(s, ctrl, steps=400):
    """Distance (m) between the two finger bodies' pads at `ctrl`, for grippers whose open fingers leave the caliper ray."""
    sides = s._gripper_sides()
    m = s.model
    d = mujoco.MjData(m)
    mujoco.mj_copyData(d, m, s.data)
    d.ctrl[s.gripper_ids[0]] = ctrl
    for _ in range(steps):
        mujoco.mj_step(m, d)
    return float(np.linalg.norm(d.geom_xpos[sides[0][-1]] - d.geom_xpos[sides[1][-1]]))


def g1_hand(s):
    """Thumb to index fingertip span with the hand in its open pose (the G1 has no single gripper motor)."""
    m = s.model
    d = mujoco.MjData(m)
    mujoco.mj_copyData(d, m, s.data)
    for a, v in zip(s.gripper_ids, np.atleast_1d(s.robot.gripper_open)):
        d.ctrl[a] = v
    for _ in range(400):
        mujoco.mj_step(m, d)
    a, b = m.body("robot/right_hand_thumb_2_link").id, m.body("robot/right_hand_index_1_link").id
    return float(np.linalg.norm(d.xpos[a] - d.xpos[b]))


def facts(name, card):
    s = build(name, card)
    r = s.robot
    item = {"id": name, "name": NAMES[name], "hands": r.hands, "mobile": bool(r.mobile), "reach": round(float(s.reach), 3),
            "footprint": round(float(s.footprint), 3), "origin": [round(float(v), 3) for v in s.origin[:2]], "rated_kg": r.payload_kg, "model_kg": None if s.payload is None else round(s.payload, 1), "gap_estimated": False}
    if len(s.gripper_ids) != 1:
        item.update(widest=round(g1_hand(s), 3), tightest=0.0, gap_estimated=True)
        return item
    lo, hi = s.model.actuator_ctrlrange[s.gripper_ids[0]]
    ctrls = np.linspace(lo, hi, 13)
    rays = np.array([s.gripper_gap(c) for c in ctrls])
    good = rays < 0.14  # a ray that misses counts as 0.15 per side: not a measurement
    if good.all():
        widest = rays.max()
    else:  # the caliper loses the fingers when wide open: scale from how far the pads move apart
        pads = np.array([tips(s, c) for c in ctrls])
        widest = (rays[good] + (pads.max() - pads[good])).max()
        item["gap_estimated"] = True
    item.update(widest=round(float(widest), 3), tightest=round(float(rays[good].min()), 3))
    return item


def job(path, title, s_robots):
    card = json.loads((ROOT / path).read_text())
    kind = card.get("kind", "pick_place")
    held = card["grip"]["object"]
    o = card["objects"][held]
    needs = card.get("needs", {})
    size = o.get("size", [card["grip"].get("width", 0.03)] * 3)
    width = card["grip"].get("width") or size[0]
    handles = o.get("handles", "none") if kind == "carry" else "none"
    volume = np.prod(size) * ({"sphere": np.pi / 6, "cylinder": np.pi / 4}.get(o.get("shape"), 1.0))
    kg = o.get("mass") or needs.get("mass_kg") or max(0.02, DENSITY * float(volume))
    place = card["success"].get("container")
    c = card["objects"].get(place, {}) if place else {}
    across = 2 * c.get("inner_radius", 0)
    if c.get("shape") == "box":
        across *= 2 ** 0.5
    out = {"title": title, "from": Path(path).parent.name + "/" + Path(path).name, "kind": kind, "width_cm": round(float(width) * 100, 1), "kg": round(float(kg), 2), "hands": int(needs.get("hands", 2 if handles == "side" else 1)),
           "move_m": float(needs.get("move_m", 0)), "handles": handles, "container_cm": round(across * 100, 1)}
    expected = {}
    for name in s_robots:
        s = build(name, card)
        label = s.refusal[0] if s.refusal else None
        if label is None:
            try:
                sample_layout(s, np.random.default_rng(0))
            except (RuntimeError, ValueError):
                label = "no_room"
        expected[name] = label
    out["python"] = expected
    return out


def main():
    card = json.loads((ROOT / "cards/cube_to_bowl.json").read_text())
    robots = [facts(n, card) for n in ORDER if n in ROBOTS]
    for f in robots:
        print({k: v for k, v in f.items() if k != "id"})
    names = [f["id"] for f in robots]
    jobs = [job(p, t, names) for p, t in [
        ("outputs/jobs/lemon_into_bowl_1cycle/card.json", "Lemon into a bowl"), ("outputs/jobs/cookie_into_plate/card.json", "Cookie onto a plate"),
        ("cards/can_to_bin.json", "Can into a bin"), ("cards/potato_to_basket.json", "Potato into a big basket"),
        ("outputs/jobs/box_two_hands/card.json", "Box with two hands"), ("cards/carry_crate.json", "Crate to the next table"), ("cards/carry_basket.json", "Basket to the next table")]]
    for j in jobs:
        print(j["title"], {k: v for k, v in j.items() if k not in ("title", "python", "from")}, j["python"])
    from translator.scene import TABLE_CENTRE, TABLE_HALF
    (ROOT / "site/public/data/facts.json").write_text(json.dumps({"robots": robots, "jobs": jobs, "table": {"centre": list(TABLE_CENTRE), "half": list(TABLE_HALF)}}, indent=1))


main()
