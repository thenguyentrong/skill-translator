"""The live loop: drag the object in the viewer while the robot works, or prove it with scripted disturbances.

  live.py ur5e --skill cube_to_bowl             # MuJoCo viewer: double-click the object, Ctrl + right-drag to move it
  live.py --proof --robots ur5e xarm7 --n 10    # replay vs live, same layouts, same disturbance -> outputs/live/proof.json
  live.py --clips                               # side-by-side and grid clips -> outputs/preview/
"""
import argparse
import json
import math
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from translator.execute import FPS, plan, reach_miss, run
from translator.live import Live, Stick, free_spot, put
from translator.perceive import Eyes
from translator.practice import ensure
from translator.scene import TABLE_TOP, build, sample_layout
from translator.translate import load_card, translate

CARDS = ROOT / "cards"
OUT = ROOT / "outputs" / "live"
CASES = {"none": "no disturbance", "a": "moved 5-10 cm mid-reach", "b": "taken away mid-descend",
         "c": "taken out of the gripper mid-carry", "d": "removed from the container after done",
         "sa": "stick shoves it mid-reach", "sb": "stick shoves it mid-descend", "sc": "stick hits it out of the gripper mid-carry"}
LABEL = {"a": "object moved", "b": "object moved away", "c": "object moved out of the gripper", "d": "object moved out of the container",
         "sa": "pushed with a stick", "sb": "pushed with a stick", "sc": "hit with a stick"}
STEP_OF = {"a": "reach", "b": "descend", "c": "carry", "sa": "reach", "sb": "descend", "sc": "carry"}
SEED = 2000


def disturb(scene, case, rng, stick=None):
    if case == "sc":
        return stick.out_of_hand(rng)
    if case in ("sa", "sb"):
        return stick.on_table(rng)
    here = scene.cube_pos()[:2]
    lo, hi = {"a": (0.05, 0.10), "b": (0.08, 0.20), "c": (0.05, 0.30), "d": (0.05, 0.30)}[case]
    xy = free_spot(scene, rng, here, lo, hi)
    if xy is None:
        return False
    put(scene, xy, 0.02 if case == "c" else 0.0)
    return True


def live_trial(scene, card, case, rng, eyes=True, seconds=60.0, after=None):
    fired = {"done": case == "none", "at": None, "hits": 0}
    step_for = STEP_OF
    stick = Stick(scene) if case.startswith("s") else None

    def on_tick(lv):
        if fired["done"]:
            if case == "sc" and fired["hits"] < 3 and lv.recoveries == 0 and lv.doing == "carry" and lv.n - fired["at"] > 12:
                fired["hits"] += 1  # the hit did not get it out of the fingers: again, like a person would
                fired["at"] = lv.n
                stick.out_of_hand(rng)
                lv.say(LABEL[case])
            if after:
                after(lv)
            return
        if case == "d":
            ready = lv.doing == "done" and lv.since >= round(0.5 * FPS) and scene.cube_in_bowl()
        else:
            ready = lv.doing == step_for[case] and lv.since > 2 and lv.dist < 0.5 * max(lv.d0, 1e-3)
        if ready:
            fired["done"] = disturb(scene, case, rng, stick) or "failed"
            fired["at"] = lv.n
            lv.say(LABEL[case])
        if after:
            after(lv)

    lv = Live(scene, card, eyes=eyes)
    ok, reason = lv.run(seconds, on_tick, keep_going=lambda: not fired["done"])
    if not fired["done"]:
        ok, reason = False, f"never reached the disturbance ({reason})"
    return lv, ok, reason, fired


def clip_joints(scene):
    """Physics leaves joints a hair outside their limits; a new plan's IK cannot start from there."""
    m, d = scene.model, scene.data
    for j in scene.joints:
        if m.jnt_limited[j]:
            a = m.jnt_qposadr[j]
            d.qpos[a] = np.clip(d.qpos[a], m.jnt_range[j][0] + 1e-6, m.jnt_range[j][1] - 1e-6)
    mujoco.mj_forward(m, d)


def replan_trial(scene, card, eyes, case, rng, seconds=60.0):
    """A stronger baseline than replay: the same plan-once path, but after each run it looks again and plans again
    until the test passes. It only reacts between runs. Stops on the simulator's test, which favours it slightly."""
    stick = Stick(scene) if case.startswith("s") else None
    history, events, used, first = [scene.data.qpos.copy()], [], 0, True
    while used < seconds * FPS:
        clip_joints(scene)
        seen = eyes.find(card)
        if any(v is None for v in seen.values()):
            return history, events, False, used
        ticks, _, _ = plan(scene, translate(card, scene, seen, check=lambda w: reach_miss(scene, w)))
        index = [i for i, t in enumerate(ticks) if t[2] == STEP_OF.get(case)] if first else []
        at = index[len(index) // 2] if index else None
        count = [0]

        def on_tick(_):
            if count[0] == at:
                disturb(scene, case, rng, stick)
                events.append((len(history) + count[0], LABEL[case]))
            count[0] += 1

        h, _ = run(scene, ticks, on_tick=on_tick)
        history += h[1:]
        used += len(h)
        if first and case == "d" and scene.cube_in_bowl():
            disturb(scene, case, rng)
            events.append((len(history), LABEL[case]))
        first = False
        if scene.cube_in_bowl():
            return history, events, True, used
    return history, events, scene.cube_in_bowl(), used


def replay_trial(scene, card, eyes, case, rng):
    """The old way, unchanged: look once, plan once, replay; the same disturbance at the same step."""
    seen = eyes.find(card)
    wps = translate(card, scene, seen, check=lambda w: reach_miss(scene, w))
    ticks, _, _ = plan(scene, wps)
    stick = Stick(scene) if case.startswith("s") else None
    index = [i for i, t in enumerate(ticks) if t[2] == STEP_OF.get(case)]
    at = index[len(index) // 2] if index else None
    count, events = [0], []

    def on_tick(_):
        if at is not None and count[0] == at:
            disturb(scene, case, rng, stick)
            events.append((count[0], LABEL[case]))
        count[0] += 1
        if hasattr(scene, "trace"):
            scene.trace.append(scene.data.mocap_pos.copy())

    history, _ = run(scene, ticks, on_tick=on_tick)
    if case == "d" and scene.cube_in_bowl():
        disturb(scene, case, rng)
        events.append((len(history), LABEL[case]))
        steps = round(1 / FPS / scene.model.opt.timestep)
        for _ in range(FPS):
            for _ in range(steps):
                mujoco.mj_step(scene.model, scene.data)
            history.append(scene.data.qpos.copy())
    return history, events, scene.cube_in_bowl()


_built = {}


def proof_job(job):
    robot, skill, case, mode, seed = job
    mujoco.set_mjcb_control(None)  # a stick left over from the last trial must not run on the next model
    card = load_card(CARDS / f"{skill}.json")
    key = (robot, skill, case.startswith("s"))
    if key not in _built:  # building a scene takes seconds; reset() clears it between trials
        _built.clear()
        _built[key] = build(robot, card, stick=key[2])
    scene = _built[key]
    cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
    scene.reset(cube, bowl, yaw)
    rng = np.random.default_rng(seed + 77)
    t0 = time.time()
    if mode == "replan":
        eyes = Eyes(scene)
        try:
            _, _, ok, used = replan_trial(scene, card, eyes, case, rng)
            reason, extra = ("ok" if ok else "failed"), {"sim_s": round(used / FPS, 1)}
        except Exception as e:
            ok, reason, extra = False, f"error: {type(e).__name__}: {e}"[:80], {}
        eyes.close()
        return {"robot": robot, "skill": skill, "case": case, "mode": mode, "seed": seed, "ok": bool(ok), "reason": reason,
                "wall": round(time.time() - t0, 1), **extra}
    if mode == "replay":
        eyes = Eyes(scene)
        try:
            _, _, ok = replay_trial(scene, card, eyes, case, rng)
            reason = "ok" if ok else "failed"
        except Exception as e:
            ok, reason = False, f"error: {type(e).__name__}: {e}"[:80]
        eyes.close()
        return {"robot": robot, "skill": skill, "case": case, "mode": mode, "seed": seed, "ok": bool(ok), "reason": reason, "wall": round(time.time() - t0, 1)}
    try:
        lv, ok, reason, fired = live_trial(scene, card, case, rng)
        out = {"sim_s": round(lv.n / FPS, 1), "recoveries": lv.recoveries, "tries": lv.tries, "rates": lv.rates(),
               "seen_mm": round(1000 * float(np.median(lv.seen_err)), 1) if lv.seen_err else None}
        lv.close()
    except Exception as e:
        ok, reason, out = False, f"error: {type(e).__name__}: {e}"[:80], {}
    return {"robot": robot, "skill": skill, "case": case, "mode": mode, "seed": seed, "ok": bool(ok), "reason": reason,
            "wall": round(time.time() - t0, 1), **out}


def proof(args):
    """Saved after every 5 results and resumable: a run stopped halfway (out of memory) loses nothing. Each worker
    process does a few trials and goes away, so memory stays flat."""
    OUT.mkdir(parents=True, exist_ok=True)
    card = load_card(CARDS / f"{args.skill}.json")
    for r in args.robots:
        ensure(r, card)
    path = OUT / f"proof_{args.skill}.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    if args.restart:
        rows = [r for r in rows if not (r["robot"] in args.robots and r["case"] in args.cases and r["mode"] in args.modes)]
    done = {(r["robot"], r["case"], r["mode"], r["seed"]) for r in rows}
    jobs = [(r, args.skill, c, mode, SEED + i) for r in args.robots for c in args.cases for mode in args.modes
            for i in range(args.n) if (r, c, mode, SEED + i) not in done]
    print(f"{len(jobs)} trials to run, {len(rows)} kept", flush=True)
    with get_context("spawn").Pool(args.workers, maxtasksperchild=12) as pool:
        results = pool.imap_unordered(proof_job, jobs)
        for k in range(len(jobs)):
            try:
                rows.append(results.next(timeout=300))  # a worker killed from outside loses its trial and would hang here
            except TimeoutError:
                path.write_text(json.dumps(rows, indent=1))
                sys.exit(f"no result for 300 s, stopped at {k}/{len(jobs)}; run again to resume")
            if k % 5 == 4:
                path.write_text(json.dumps(rows, indent=1))
                print(f"{k + 1}/{len(jobs)}", flush=True)
    path.write_text(json.dumps(rows, indent=1))
    print(table(rows))


def table(rows):
    robots = list(dict.fromkeys(r["robot"] for r in rows))
    modes = [m for m in ("replay", "replan", "live") if any(x["mode"] == m for x in rows)]
    lines = ["| disturbance | " + " | ".join(f"{r} {m}" for r in robots for m in modes) + " |"]
    lines.append("|---|" + "---|" * (len(modes) * len(robots)))
    for case, text in CASES.items():
        cells = []
        for r in robots:
            for mode in modes:
                sel = [x for x in rows if x["robot"] == r and x["case"] == case and x["mode"] == mode]
                cells.append(f"{sum(x['ok'] for x in sel)}/{len(sel)}" if sel else "-")
        lines.append(f"| {text} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BG = (18, 20, 24)
AMBER = (242, 183, 5)


def render_run(scene, history, size, trace=None):
    m = scene.model
    d = mujoco.MjData(m)
    cam = scene.camera()
    tall = max(0.0, scene.origin[2] - TABLE_TOP - 0.3)
    cam.distance = 1.5 * scene.reach + 0.35 + 1.6 * tall
    cam.lookat[:] = [scene.origin[0] + 0.5 * scene.reach, scene.origin[1], cam.lookat[2] + 0.5 * tall]
    frames = []
    with mujoco.Renderer(m, size[1], size[0]) as r:
        for i, q in enumerate(history):
            d.qpos[:] = q
            if trace:  # the stick is kinematic, so it is not in qpos
                d.mocap_pos[:] = trace[min(i, len(trace) - 1)]
            mujoco.mj_forward(m, d)
            r.update_scene(d, camera=cam)
            frames.append(r.render().copy())
    return frames


def record(robot, skill, case, mode, seed, size):
    """One trial -> frames, [(tick, text)], ok."""
    card = load_card(CARDS / f"{skill}.json")
    scene = build(robot, card, stick=case.startswith("s"))
    cube, bowl, yaw = sample_layout(scene, np.random.default_rng(seed))
    scene.reset(cube, bowl, yaw)
    rng = np.random.default_rng(seed + 77)
    trace = [scene.data.mocap_pos.copy()]
    if mode == "replay":
        eyes = Eyes(scene)
        scene.trace = trace
        history, events, ok = replay_trial(scene, card, eyes, case, rng)
        eyes.close()
    else:
        history = [scene.data.qpos.copy()]

        def after(_):
            history.append(scene.data.qpos.copy())
            trace.append(scene.data.mocap_pos.copy())

        lv, ok, _, _ = live_trial(scene, card, case, rng, after=after)
        events = list(lv.events)
        lv.close()
    frames = render_run(scene, history, size, trace if case.startswith("s") else None)
    mujoco.set_mjcb_control(None)
    return frames, events, ok


def pick_seed(robot, skill, case):
    """A trial the proof table counts as a recovery (the clip shows one trial; the table has all of them)."""
    path = OUT / f"proof_{skill}.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    good = [r for r in rows if r["robot"] == robot and r["case"] == case and r["mode"] == "live" and r["ok"]
            and (r.get("recoveries", 0) > 0 or case in ("sa", "sb", "a", "b"))]
    lost = {r["seed"] for r in rows if r["robot"] == robot and r["case"] == case and r["mode"] == "replay" and not r["ok"]}
    both = [r for r in good if r["seed"] in lost]  # the hit also got through on the replay side
    return min(r["seed"] for r in both or good) if good else SEED


def banner(frame, events, tick, font, end=None):
    """The latest event for 2.5 s, in a dark strip at the bottom of the frame."""
    im = Image.fromarray(frame)
    d = ImageDraw.Draw(im)
    text = next((t for n, t in reversed(events) if n <= tick < n + 2.5 * FPS), None)
    if end:
        text = end
    if text:
        w = d.textlength(text, font=font)
        h = font.size + 14
        d.rectangle([0, im.height - h, im.width, im.height], fill=BG)
        d.text(((im.width - w) / 2, im.height - h + 5), text, fill=AMBER, font=font)
    return np.asarray(im)


def side_by_side(robot, skill, case, seed):
    size = (632, 474)
    left, ev_l, ok_l = record(robot, skill, case, "replay", seed, size)
    right, ev_r, ok_r = record(robot, skill, case, "live", seed, size)
    n = max(len(left), len(right)) + 2 * FPS
    title = ImageFont.truetype(SANS, 30)
    small = ImageFont.truetype(SANS, 24)
    frames = []
    for i in range(n):
        im = Image.new("RGB", (1280, 720), BG)
        d = ImageDraw.Draw(im)
        d.text((40, 24), f"{robot}: {CASES[case]}", fill=(255, 255, 255), font=title)
        d.text((8, 104), "Plan once, then replay", fill=(200, 205, 210), font=small)
        d.text((648, 104), "Live loop, driven by the card", fill=(200, 205, 210), font=small)
        a, b = min(i, len(left) - 1), min(i, len(right) - 1)
        end_l = ("in the bowl" if ok_l else "not in the bowl") if i >= len(left) else None
        end_r = ("in the bowl" if ok_r else "not in the bowl") if i >= len(right) else None
        im.paste(Image.fromarray(banner(left[a], ev_l, a, small, end_l)), (4, 146))
        im.paste(Image.fromarray(banner(right[b], ev_r, b, small, end_r)), (644, 146))
        frames.append(np.asarray(im))
    return frames, ok_l, ok_r


def clips(args):
    out = ROOT / "outputs" / "preview"
    out.mkdir(parents=True, exist_ok=True)
    everything = []
    for case in ("sa", "sb", "sc", "d"):
        frames, ok_l, ok_r = side_by_side(args.clip_robot, args.skill, case, pick_seed(args.clip_robot, args.skill, case))
        imageio.mimsave(out / f"live_vs_replay_{case}.mp4", frames, fps=FPS, codec="libx264", quality=7, macro_block_size=8)
        print(case, "replay", ok_l, "live", ok_r, len(frames) / FPS, "s", flush=True)
        everything += frames
    imageio.mimsave(out / "live_vs_replay.mp4", everything, fps=FPS, codec="libx264", quality=7, macro_block_size=8)
    size = (420, 300)
    font = ImageFont.truetype(SANS, 18)
    runs = []
    for robot in args.grid:
        frames, events, ok = record(robot, args.skill, "sc", "live", pick_seed(robot, args.skill, "sc"), size)
        print(robot, "live", ok, len(frames) / FPS, "s", flush=True)
        runs.append((robot, frames, events))
    n = max(len(f) for _, f, _ in runs) + 2 * FPS
    title = ImageFont.truetype(SANS, 30)
    grid = []
    for i in range(n):
        im = Image.new("RGB", (1280, 720), BG)
        ImageDraw.Draw(im).text((40, 24), "Hit out of the gripper with a stick: each robot picks it up again", fill=(255, 255, 255), font=title)
        for k, (robot, frames, events) in enumerate(runs):
            j = min(i, len(frames) - 1)
            tile = Image.fromarray(banner(frames[j], events, j, font))
            x, y = 7 + (k % 3) * 424, 86 + (k // 3) * 316
            im.paste(tile, (x, y))
            ImageDraw.Draw(im).text((x + 8, y + 6), robot, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        grid.append(np.asarray(im))
    imageio.mimsave(out / "live_grid.mp4", grid, fps=FPS, codec="libx264", quality=7, macro_block_size=8)
    print("saved", out)


def viewer(args):
    import mujoco.viewer
    card = load_card(CARDS / f"{args.skill}.json")
    ensure(args.robot, card)
    scene = build(args.robot, card)
    if scene.refusal:
        sys.exit(f"{args.robot}: {scene.refusal[1]}")
    cube, bowl, yaw = sample_layout(scene, np.random.default_rng(args.seed))
    with mujoco.viewer.launch_passive(scene.model, scene.data, show_left_ui=False, show_right_ui=False) as v:
        v.cam.lookat[:] = [scene.origin[0] + 0.45 * scene.reach, scene.origin[1], TABLE_TOP + 0.08]
        v.cam.distance, v.cam.azimuth, v.cam.elevation = 1.9 * scene.reach + 0.25, 145, -25
        with v.lock():
            scene.reset(cube, bowl, yaw)
        lv = Live(scene, card, eyes=not args.true_pose)
        start = time.perf_counter()
        while v.is_running() and (args.seconds is None or lv.n < args.seconds * FPS):
            with v.lock():  # the mouse: double-click the object, Ctrl + right-drag pulls it, Ctrl + left-drag turns it
                scene.data.xfrc_applied[:] = 0
                mujoco.mjv_applyPerturbForce(scene.model, scene.data, v.perturb)
                lv.step()
            state = lv.state()
            v.set_texts((mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                         "Robot\nSkill\nStep\nEyes\nLast", f"{args.robot}\n{card['name']}\n{state['step']}\n"
                         f"{'cameras' if lv.eyes else 'TRUE POSE (not cameras)'}\n{state['last']}"))
            v.sync()
            wait = start + lv.n / FPS - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
        print(json.dumps(lv.rates()), f"ticks {lv.n}, behind real time by {max(0.0, time.perf_counter() - start - lv.n / FPS):.1f} s")
        lv.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("robot", nargs="?")
    p.add_argument("--skill", default="cube_to_bowl")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--seconds", type=float, default=None, help="stop the viewer after this long")
    p.add_argument("--true-pose", action="store_true", help="read the simulator instead of the cameras (for testing)")
    p.add_argument("--proof", action="store_true")
    p.add_argument("--robots", nargs="*", default=["ur5e"])
    p.add_argument("--cases", nargs="*", default=list(CASES))
    p.add_argument("--modes", nargs="*", default=["replay", "live"])
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--restart", action="store_true", help="drop saved results of these robots/cases/modes first")
    p.add_argument("--clips", action="store_true")
    p.add_argument("--clip-robot", default="ur5e")
    p.add_argument("--clip-seed", type=int, default=0)
    p.add_argument("--grid", nargs="*", default=["ur5e", "xarm7", "fr3", "tienkung3", "g1", "so101"])
    args = p.parse_args()
    if args.clips:
        return clips(args)
    if args.proof:
        return proof(args)
    viewer(args)


if __name__ == "__main__":
    main()
