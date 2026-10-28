"""Practice: before a robot is tested on a skill, it tries the grip a few times in simulation.

The card says where to hold the object, not how deep each gripper must go: a Robotiq's pads close on an arc,
the SO-101 has one fixed jaw, a lemon rolls where a cube sits. So the robot tries a few grip depths on practice
layouts (seeds far away from the test seeds) and keeps the depth that holds most often. Done once per robot and skill.
"""
import json
import time
from multiprocessing import Pool

import numpy as np

from .execute import run_skill
from .robots import get
from .scene import build, practice_file, sample_layout

DEPTHS = (-0.010, -0.005, 0.0, 0.005, 0.010, 0.020)
CARRY_DEPTHS = (0.0, 0.010, 0.020)  # below the handle bar's centre; a carry trial is ~1 min of simulated time
SEED = 90000


def _try(job):
    robot, card, depth, seed = job
    try:
        scene = build(robot, card, grip_depth=depth)
        cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
        scene.reset(cube, bowl, yaw)
        return depth, run_skill(scene, card, scene.true_objects()).reason
    except Exception as e:
        return depth, f"error: {e}"[:300]


def practice(robot, card, depths=None, n=None, workers=30, save=True):
    """Returns {"grip_depth": best, "tries": {depth: {reason: count}}, ...} and saves it for build()."""
    t0 = time.time()
    carry = card.get("kind") == "carry"
    depths = depths or (CARRY_DEPTHS if carry else DEPTHS)
    n = n or (6 if carry else 12)
    robot = get(robot).name
    jobs = [(robot, card, d, SEED + i) for d in depths for i in range(n)]
    with Pool(min(workers, len(jobs))) as pool:
        results = pool.map(_try, jobs)
    tries = {d: {} for d in depths}
    for d, reason in results:
        tries[d][reason] = tries[d].get(reason, 0) + 1
    best = max(depths, key=lambda d: (tries[d].get("ok", 0), -abs(d - (0.01 if carry else 0.0))))
    out = {"robot": robot, "card": card["name"], "grip_depth": best, "n": n,
           "success": tries[best].get("ok", 0), "tries": {f"{d * 1000:+.0f} mm": t for d, t in tries.items()},
           "seconds": round(time.time() - t0, 1)}
    if save:
        f = practice_file(robot, card)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out, indent=1))
    return out


def ensure(robot, card, **kw):
    """The saved practice result, or practise now."""
    f = practice_file(get(robot).name, card)
    if f.exists():
        return json.loads(f.read_text())
    return practice(robot, card, **kw)
