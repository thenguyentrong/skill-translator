"""Raw robot meshes -> one small binary for the page: site/public/models/<robot>.bin + <robot>.json"""
import json
import sys
from pathlib import Path

import fast_simplification
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "site" / "tools" / "raw"
OUT = ROOT / "site" / "public" / "models"


def weld(v, f):
    key = np.round(v / 1e-5).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    f = inverse.reshape(-1)[f]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    return v[first], f


def run(name, keep=0.4, floor=300):
    d = np.load(RAW / f"{name}.npz")
    meta = json.loads((RAW / f"{name}.json").read_text())
    blobs, table, off = [], [], 0
    for i in range(meta["meshes"]):
        v, f = weld(d[f"v{i}"].astype(np.float64), d[f"f{i}"])
        if len(f) > floor:
            reduction = max(0.0, 1.0 - max(keep, floor / len(f)))
            v2, f2 = fast_simplification.simplify(v.astype(np.float32), f.astype(np.int32), target_reduction=reduction)
            v, f = v2, f2
        vb = np.asarray(v, dtype=np.float32).tobytes()
        ib = np.asarray(f, dtype=np.uint32).tobytes()
        table.append({"v": [off, len(v)], "i": [off + len(vb), f.size]})
        blobs += [vb, ib]
        off += len(vb) + len(ib)
    (OUT / f"{name}.bin").write_bytes(b"".join(blobs))
    meta["mesh_table"] = table
    (OUT / f"{name}.json").write_text(json.dumps(meta))
    print(name, "bin KB", off // 1024, "tris", sum(t["i"][1] for t in table) // 3)


for n in sys.argv[1:] or ["ur5e"]:
    run(n)
