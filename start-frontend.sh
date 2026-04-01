#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL:-http://127.0.0.1:7860}"

cd "${ROOT_DIR}/frontend"

if [ ! -d "node_modules" ]; then
  npm install
fi

HOST="${FRONTEND_HOST}" \
PORT="${FRONTEND_PORT}" \
BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL}" \
npm run dev
