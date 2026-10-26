"""Checks that MuJoCo, mink and offscreen rendering work on this machine."""
from importlib.metadata import version

import mujoco
import mink
import numpy as np

XML = """
<mujoco>
  <worldbody>
    <light pos="0 0 2"/>
    <geom type="plane" size="1 1 .1"/>
    <body pos="0 0 .2">
      <freejoint/>
      <geom type="box" size=".02 .02 .02"/>
    </body>
  </worldbody>
</mujoco>
"""

m = mujoco.MjModel.from_xml_string(XML)
d = mujoco.MjData(m)
for _ in range(500):
    mujoco.mj_step(m, d)
r = mujoco.Renderer(m, 240, 320)
r.update_scene(d)
img = r.render()
r.close()
print("mujoco", mujoco.__version__, "| mink", version("mink"))
print("box rests at z =", round(float(d.qpos[2]), 4), "(expect ~0.02)")
print("render", img.shape, "mean", int(np.mean(img)))
