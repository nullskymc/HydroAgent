#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-7860}"
FRONTEND_ORIGINS="${FRONTEND_ORIGINS:-http://127.0.0.1:3000,http://localhost:3000}"

cd "${ROOT_DIR}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

. ".venv/bin/activate"

if [ ! -x ".venv/bin/uvicorn" ]; then
  pip install -r requirements.txt
fi

APP_HOST="${BACKEND_HOST}" \
APP_PORT="${BACKEND_PORT}" \
FRONTEND_ORIGINS="${FRONTEND_ORIGINS}" \
python3 src/main.py
