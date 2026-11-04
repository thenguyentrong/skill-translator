"""Scene + robot -> browser files: physics model (.mjb, visual meshes dropped) and a raw mesh dump for drawing.

  .venv/bin/python site/tools/export_models.py ur5e panda
  uv run --with fast-simplification --with numpy site/tools/decimate.py ur5e panda
"""
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from translator import scene as S

OUT = ROOT / "site" / "public" / "models"
RAW = ROOT / "site" / "tools" / "raw"
NO_COLLISION = {"xarm7": "robot/link"}  # arm links that collide with their full meshes and never touch anything here


def export(name, card_path="cards/cube_to_bowl.json"):
    card = json.loads((ROOT / card_path).read_text())
    captured = {}
    real = S.Scene

    def spy(*a, **k):  # build() keeps its spec local; grab it from the caller's frame
        captured["spec"] = sys._getframe(1).f_locals["spec"]
        return real(*a, **k)

    S.Scene = spy
    s = S.build(name, card)
    S.Scene = real
    m = s.model
    spec = captured["spec"]
    spec.compiler.discardvisual = True
    for t in list(spec.textures):  # the skybox alone is 9 MB
        spec.delete(t)
    if name in NO_COLLISION:
        for g in list(spec.geoms):
            if g.meshname.startswith(NO_COLLISION[name]):
                mesh = g.meshname
                spec.delete(g)
                spec.delete(spec.mesh(mesh))
    phys = spec.compile()
    # the gripper's mount and base collide with their full 30k-vertex meshes: a box is plenty up at the wrist
    big = {k: phys.mesh(k).name for k in range(phys.nmesh) if phys.mesh_vertnum[k] > 4000}
    for g in list(spec.geoms):
        if g.meshname in big.values():
            c = next(i for i in range(phys.ngeom) if phys.geom_dataid[i] >= 0 and phys.mesh(phys.geom_dataid[i]).name == g.meshname)
            quat, centre, half = phys.geom_quat[c].copy(), phys.geom_aabb[c, :3], phys.geom_aabb[c, 3:]
            R = np.zeros(9)
            mujoco.mju_quat2Mat(R, quat)
            g.type, g.meshname = mujoco.mjtGeom.mjGEOM_BOX, ""
            g.size, g.pos, g.quat = half.copy(), phys.geom_pos[c] + R.reshape(3, 3) @ centre, quat
    for mesh in big.values():
        spec.delete(spec.mesh(mesh))
    phys = spec.compile()
    for g in s.gripper_ids:  # build() tunes grip force after compiling
        i = phys.actuator(m.actuator(g).name).id
        phys.actuator_gainprm[i], phys.actuator_biasprm[i] = m.actuator_gainprm[g], m.actuator_biasprm[g]
    OUT.mkdir(parents=True, exist_ok=True)
    mujoco.mj_saveModel(phys, str(OUT / f"{name}.mjb"))

    geoms, used = [], {}
    for g in range(m.ngeom):
        body = m.body(m.geom_bodyid[g]).name
        if not body.startswith(S.PREFIX) or m.geom_group[g] >= 3 or m.geom_rgba[g, 3] == 0:
            continue
        mat = m.geom_matid[g]
        rgba = m.mat_rgba[mat] if mat >= 0 else m.geom_rgba[g]
        kind = int(m.geom_type[g])
        item = {"body": body, "pos": m.geom_pos[g].round(6).tolist(), "quat": m.geom_quat[g].round(6).tolist(),
                "rgba": [round(float(v), 3) for v in rgba], "type": kind, "size": m.geom_size[g].round(5).tolist()}
        if kind == int(mujoco.mjtGeom.mjGEOM_MESH):
            k = int(m.geom_dataid[g])
            used.setdefault(k, len(used))
            item["mesh"] = used[k]
        geoms.append(item)
    RAW.mkdir(parents=True, exist_ok=True)
    arrays = {}
    for k, i in used.items():
        va, vn = m.mesh_vertadr[k], m.mesh_vertnum[k]
        fa, fn = m.mesh_faceadr[k], m.mesh_facenum[k]
        arrays[f"v{i}"] = m.mesh_vert[va:va + vn].astype(np.float32)
        arrays[f"f{i}"] = m.mesh_face[fa:fa + fn].astype(np.int32)
    np.savez(RAW / f"{name}.npz", **arrays)

    acts = [a for a in s.arm_actuators if m.actuator_trntype[a] == int(mujoco.mjtTrn.mjTRN_JOINT)]
    joints = [int(m.actuator_trnid[a, 0]) for a in acts]
    meta = {
        "name": name, "site": m.site(s.ee_site_id).name, "acts": [m.actuator(a).name for a in acts],
        "joints": [m.joint(j).name for j in joints], "grip_acts": [m.actuator(a).name for a in s.gripper_ids],
        "open": np.atleast_1d(s.open_ctrl).tolist(), "closed": np.atleast_1d(s.close_ctrl).tolist(),
        "home": {k: float(v) for k, v in s.home.items()}, "approach": s.robot.approach_axis, "closing": s.robot.closing_axis,
        "grip_offset": list(s.robot.grip_offset), "fixed_jaw": bool(s.robot.fixed_jaw), "orientation_cost": s.robot.orientation_cost,
        "reach": float(s.reach), "footprint": float(s.footprint), "origin": s.origin.tolist(), "grip_depth": float(s.grip_depth),
        "tip_reach": float(s.tip_reach), "table_top": S.TABLE_TOP, "table_centre": list(S.TABLE_CENTRE), "table_half": list(S.TABLE_HALF),
        "held_half": float(s.held_half), "bowl_radius": float(s.bowl_radius), "bowl_wall": float(s.bowl_wall),
        "held_width": float(card["grip"].get("width", 0.03)), "card": card, "geoms": geoms, "meshes": len(used),
    }
    (RAW / f"{name}.json").write_text(json.dumps(meta))
    print(name, "mjb MB", round((OUT / f"{name}.mjb").stat().st_size / 1e6, 2), "ngeom", phys.ngeom, "visual geoms", len(geoms),
          "meshes", len(used), "faces", sum(len(v) for k, v in arrays.items() if k[0] == "f"))


for n in sys.argv[1:] or ["ur5e"]:
    export(n)
