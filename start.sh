#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-7860}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
FRONTEND_ORIGINS="${FRONTEND_ORIGINS:-http://${FRONTEND_HOST}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}}"
BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
}

trap 'printf "\nStopping HydroAgent services...\n"; cleanup' EXIT INT TERM

printf "Starting HydroAgent backend + Next.js frontend...\n"

cd "${ROOT_DIR}"

if [ ! -d ".venv" ]; then
  printf "Creating Python virtual environment...\n"
  python3 -m venv .venv
fi

. ".venv/bin/activate"

if [ ! -x ".venv/bin/uvicorn" ]; then
  printf "Installing backend dependencies...\n"
  pip install -r requirements.txt
fi

APP_HOST="${BACKEND_HOST}" \
APP_PORT="${BACKEND_PORT}" \
FRONTEND_ORIGINS="${FRONTEND_ORIGINS}" \
python3 src/main.py &
BACKEND_PID=$!

printf "Backend running at http://%s:%s (PID %s)\n" "${BACKEND_HOST}" "${BACKEND_PORT}" "${BACKEND_PID}"

cd "${ROOT_DIR}/frontend"

if [ ! -d "node_modules" ]; then
  printf "Installing frontend dependencies...\n"
  npm install
fi

HOST="${FRONTEND_HOST}" \
PORT="${FRONTEND_PORT}" \
BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL}" \
npm run dev &
FRONTEND_PID=$!

printf "Frontend running at http://%s:%s (PID %s)\n" "${FRONTEND_HOST}" "${FRONTEND_PORT}" "${FRONTEND_PID}"
printf "Health check: http://%s:%s/api/health\n" "${BACKEND_HOST}" "${BACKEND_PORT}"

wait "${BACKEND_PID}" "${FRONTEND_PID}"
