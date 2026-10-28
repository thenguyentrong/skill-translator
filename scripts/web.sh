#!/usr/bin/env bash
# Local web app: http://127.0.0.1:8000
cd "$(dirname "$0")/.." && exec .venv/bin/python -m web.app
