"""Geometric grasp design for the G1 Dex3 hand.

Searches open/close hand poses, the grip point and the hand's turn so that thumb and finger touch
opposite cube faces at the same moment, near the face centres, at mid-height, with flat pads
(horizontal push), and nothing touches the table or the cube before that. Writes the best designs to
outputs/grasp_design_<cube mm>.json. Then check them in physics with rig.score(...) (vision errors included).
The G1 adapter values in translator/robots.py come from this search + the physics check; a rerun can
land on a slightly different but equally valid design.
"""
import sys, json, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np, mujoco, rig

m = rig.build()
d = mujoco.MjData(m)
cube_g, table_g = m.geom("cube").id, m.geom("table").id
cq = m.jnt_qposadr[m.joint("cube").id]
hand_q = [m.jnt_qposadr[m.joint(f"h/right_hand_{j}_joint").id] for j in rig.DEX3]
wb = m.body("h/right_wrist_yaw_link").id
def group(prefixes):
    return [g for g in range(m.ngeom) if m.geom_contype[g] and any(m.body(m.geom_bodyid[g]).name.startswith(p) for p in prefixes)]
THUMB = group(["h/right_hand_thumb_1", "h/right_hand_thumb_2"])
FINGER = group(["h/right_hand_index", "h/right_hand_middle"])
PALM = group(["h/right_wrist_yaw_link", "h/right_hand_thumb_0"])
ALL = THUMB + FINGER + PALM
ft = np.zeros(6)

def dist(gs, other):
    best, pts = 1.0, None
    for g in gs:
        dd = mujoco.mj_geomDistance(m, d, g, other, 0.2, ft)
        if dd < best:
            best, pts = dd, ft.copy()
    return best, pts

PSI = [0.0]


def place(grip, psi=None):
    psi = PSI[0] if psi is None else psi
    d.qpos[cq:cq + 7] = [0, 0, rig.HALF, np.cos(psi / 2), 0, 0, np.sin(psi / 2)]
    rig.set_palm(m, d, np.array([0, 0, rig.HALF]), grip, qpos=True)


def evaluate(o, c, grip, steps=26):
    """Returns (score, info). Higher is better. Penalties are graded so a search can follow them."""
    place(grip)
    o, c = np.array(o), np.array(c)
    s_t = s_f = None
    last_t = last_f = np.zeros(3)
    info, pen = {}, 0.0
    for i, s in enumerate(np.linspace(0, 1, steps)):
        d.qpos[hand_q] = o + s * (c - o)
        mujoco.mj_kinematics(m, d)
        pen += max(0.0, 0.002 - dist(ALL, table_g)[0]) * 200
        if i == 0:
            pen += max(0.0, 0.004 - dist(ALL, cube_g)[0]) * 200
            continue
        pen += max(0.0, 0.0005 - dist(PALM, cube_g)[0]) * 200
        dt, pt = dist(THUMB, cube_g)
        df, pf = dist(FINGER, cube_g)
        if s_t is None and dt < 0.0005:
            s_t, info["thumb_contact"] = s, pt[3:].copy()
            info["thumb_n"] = last_t
        if s_f is None and df < 0.0005:
            s_f, info["finger_contact"] = s, pf[3:].copy()
            info["finger_n"] = last_f
        if dt > 0.0005:
            last_t = (pt[3:] - pt[:3]) / max(np.linalg.norm(pt[3:] - pt[:3]), 1e-9)
        if df > 0.0005:
            last_f = (pf[3:] - pf[:3]) / max(np.linalg.norm(pf[3:] - pf[:3]), 1e-9)
        if s_t is not None and s_f is not None:
            break
    if s_t is None or s_f is None:
        miss = (0 if s_t is not None else max(dt, 0)) + (0 if s_f is not None else max(df, 0))
        return -10 - pen - miss * 100, {"why": "no contact", "pen": pen}
    rz = np.array([[np.cos(PSI[0]), np.sin(PSI[0])], [-np.sin(PSI[0]), np.cos(PSI[0])]])
    (xt, yt), (xf, yf) = rz @ info["thumb_contact"][:2], rz @ info["finger_contact"][:2]
    zt, zf = info["thumb_contact"][2], info["finger_contact"][2]
    # which face each one touches (cube frame): the larger horizontal coordinate, with its sign
    ft_ax, ff_ax = int(abs(yt) > abs(xt)), int(abs(yf) > abs(xf))
    pt, pf = (xt, yt), (xf, yf)
    opposite = ft_ax == ff_ax and np.sign(pt[ft_ax]) != np.sign(pf[ff_ax])
    side = 0.0 if opposite else 5.0
    off_t, off_f = abs(pt[1 - ft_ax]), abs(pf[1 - ff_ax])
    centred = max(0.0, off_t - 0.4 * rig.HALF) / 0.004 + max(0.0, off_f - 0.8 * rig.HALF) / 0.004
    tilt = max(0.0, abs(info["thumb_n"][2]) - 0.15) * 20 + max(0.0, abs(info["finger_n"][2]) - 0.15) * 20
    score = -pen - side - centred - tilt - abs(s_t - s_f) * 5 - abs(zt - rig.HALF) / 0.005 - abs(zf - rig.HALF) / 0.005
    info.update(s_t=s_t, s_f=s_f, zt_mm=zt * 1000, zf_mm=zf * 1000, axis="xy"[ft_ax], off_t_mm=off_t * 1000, off_f_mm=off_f * 1000, nz_t=float(info["thumb_n"][2]), nz_f=float(info["finger_n"][2]), pen=pen, side=side)
    info["feasible"] = pen == 0 and side == 0
    return score, info


def unpack(v):
    pose = lambda p: [p[0], p[1], p[2], p[3], p[4], p[3], p[4]]
    PSI[0] = v[13]
    return pose(v[:5]), pose(v[5:10]), np.array([v[10], v[11], v[12]])

if __name__ == "__main__":
    OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "outputs/grasp_design_%d.json") % round(rig.HALF * 2000)
    lo = np.array([-1.05, -1.05, -1.75, 0.0, 0.0] * 2 + [0.10, 0.03, -0.045, -1.0])
    hi = np.array([1.05, 0.72, 0.0, 1.57, 1.75] * 2 + [0.20, 0.12, 0.045, 1.0])
    rng = np.random.default_rng(1)
    # analytic start: fingers bent ~90 deg with tips beside the far face, thumb pointing along the hand
    mean = np.array([0.0, -0.3, -1.2, 0.15, 1.2, 0.0, -0.9, -0.6, 0.6, 1.2, 0.130, 0.060 + (rig.HALF - 0.015), 0.0, 0.0])
    std = np.array([0.5] * 10 + [0.02, 0.015, 0.012, 0.3])
    keep, t0 = [], time.time()
    for it in range(40):
        pop = np.clip(mean + std * rng.standard_normal((500, 14)), lo, hi)
        res = [evaluate(*unpack(v)) for v in pop]
        sc = np.array([r[0] for r in res])
        feas = np.array([r[1].get("feasible", False) for r in res])
        idx = np.argsort(-sc)[:50]
        elite = pop[idx]
        mean, std = elite.mean(0), np.maximum(elite.std(0), np.r_[[0.03] * 10, [0.002] * 3, [0.02]])
        keep += [(sc[i], pop[i]) for i in idx[:10] if feas[i]]
        print(f"round {it}: feasible {feas.sum()}/500, best {sc.max():.2f}, best feasible {sc[feas].max() if feas.any() else float('nan'):.2f}  ({time.time() - t0:.0f} s)", flush=True)
    keep.sort(key=lambda x: -x[0])
    out = []
    seen = set()
    for s, v in keep:
        k = tuple(np.round(v, 2))
        if k in seen: continue
        seen.add(k); out.append({"score": float(s), "v": v.tolist(), "info": {k2: (np.round(v2, 4).tolist() if hasattr(v2, "tolist") else v2) for k2, v2 in evaluate(*unpack(v))[1].items()}})
        if len(out) == 40: break
    json.dump(out, open(OUT, "w"), indent=1)
    for r in out[:5]: print(round(r["score"], 2), r["info"])
