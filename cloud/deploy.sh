#!/usr/bin/env bash
# Sends the Meta key to Modal's secret store, then deploys. Run again after a code change.
set -euo pipefail
cd "$(dirname "$0")/.."
meta=$(grep '^MODEL_API_KEY=' .env | cut -d= -f2-)
modal secret create --force translator-meta "MODEL_API_KEY=$meta" >/dev/null
modal deploy cloud/modal_app.py
