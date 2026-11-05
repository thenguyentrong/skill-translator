#!/usr/bin/env bash
# Sends the Meta key and the access code to Modal's secret store, then deploys. Run again after a code change.
set -euo pipefail
cd "$(dirname "$0")/.."
grep -q '^ACCESS_CODE=' .env || echo "ACCESS_CODE=$(openssl rand -hex 8)" >> .env
meta=$(grep '^MODEL_API_KEY=' .env | cut -d= -f2-)
code=$(grep '^ACCESS_CODE=' .env | cut -d= -f2-)
modal secret create --force translator-meta "MODEL_API_KEY=$meta" >/dev/null
modal secret create --force translator-web "ACCESS_CODE=$code" >/dev/null
modal deploy cloud/modal_app.py
