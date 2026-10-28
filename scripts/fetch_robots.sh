#!/usr/bin/env bash
# Fetches the robot models into assets/robots/ (sparse clones, no history).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/assets/robots"
mkdir -p "$DEST"

sparse_clone() {
  local url="$1" dir="$2"; shift 2
  if [ ! -d "$dir/.git" ]; then
    git clone --depth 1 --filter=blob:none --sparse "$url" "$dir"
  fi
  git -C "$dir" sparse-checkout set "$@"
  git -C "$dir" log -1 --format="%h %cs $url" > "$dir/REVISION"
}

sparse_clone https://github.com/google-deepmind/mujoco_menagerie.git "$DEST/mujoco_menagerie" \
  franka_emika_panda universal_robots_ur5e robotiq_2f85 unitree_g1 kinova_gen3 ufactory_xarm7 \
  ufactory_lite6 pal_talos booster_t1 rainbow_robotics_rby1 franka_fr3 rethink_robotics_sawyer universal_robots_ur10e

sparse_clone https://github.com/TheRobotStudio/SO-ARM100.git "$DEST/SO-ARM100" \
  Simulation/SO101

# humanoids from their makers (all Apache-2.0)
sparse_clone https://github.com/limxdynamics/humanoid-description.git "$DEST/limx_humanoid" \
  HU_D04_description
sparse_clone https://github.com/Open-X-Humanoid/xSIM_MUJOCO.git "$DEST/tienkung_xsim" \
  resources/tiangong3

# Oli with LimX's own grippers (they ship it as URDF only): HU_D04_01_gripper.xml next to the official MJCF
"$(dirname "$0")/../.venv/bin/python" "$(dirname "$0")/limx_gripper.py"

cat "$DEST"/*/REVISION
