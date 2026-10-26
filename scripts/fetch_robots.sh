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
  franka_emika_panda universal_robots_ur5e robotiq_2f85 unitree_g1 kinova_gen3 ufactory_xarm7

sparse_clone https://github.com/TheRobotStudio/SO-ARM100.git "$DEST/SO-ARM100" \
  Simulation/SO101

cat "$DEST"/*/REVISION
