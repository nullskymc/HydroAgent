#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-7860}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
FRONTEND_ORIGINS="${FRONTEND_ORIGINS:-http://${FRONTEND_HOST}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}}"
BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

INSTALL_BACKEND_DEPS="${INSTALL_BACKEND_DEPS:-auto}"
INSTALL_FRONTEND_DEPS="${INSTALL_FRONTEND_DEPS:-auto}"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/logs/dev}"
case "${LOG_DIR}" in
  /*) ;;
  *) LOG_DIR="${ROOT_DIR}/${LOG_DIR}" ;;
esac

BACKEND_PID=""
FRONTEND_PID=""
STARTED_PIDS=()
STOPPING=0

usage() {
  cat <<'EOF'
Usage:
  ./start.sh [all|backend|frontend]

Environment:
  PYTHON_BIN             Python command, default: python3
  BACKEND_HOST           Backend host, default: 127.0.0.1
  BACKEND_PORT           Backend port, default: 7860
  FRONTEND_HOST          Frontend host, default: 127.0.0.1
  FRONTEND_PORT          Frontend port, default: 3000
  FRONTEND_ORIGINS       CORS origins passed to FastAPI
  BACKEND_API_BASE_URL   Backend URL used by Next.js server routes
  INSTALL_BACKEND_DEPS   auto|always|never, default: auto
  INSTALL_FRONTEND_DEPS  auto|always|never, default: auto
  LOG_DIR                Log directory, default: ./logs/dev
EOF
}

log() {
  printf "[HydroAgent] %s\n" "$*"
}

fail() {
  printf "[HydroAgent] ERROR: %s\n" "$*" >&2
  exit 1
}

require_mode() {
  case "${MODE}" in
    all | backend | frontend | -h | --help) ;;
    *) fail "Unsupported mode '${MODE}'. Use all, backend, or frontend." ;;
  esac
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

validate_install_policy() {
  case "$1" in
    auto | always | never) ;;
    *) fail "$2 must be one of: auto, always, never" ;;
  esac
}

port_owner() {
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi

  lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null \
    | awk 'NR > 1 {print $1 " pid=" $2 " addr=" $9}' \
    | head -n 1 || true
}

require_free_port() {
  local port="$1"
  local label="$2"
  local owner

  owner="$(port_owner "${port}")"
  if [ -n "${owner}" ]; then
    fail "${label} port ${port} is already in use by ${owner}"
  fi
}

prepare_log_dir() {
  mkdir -p "${LOG_DIR}"
}

prepare_backend_env() {
  cd "${ROOT_DIR}"
  require_command "${PYTHON_BIN}"

  if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment at .venv"
    "${PYTHON_BIN}" -m venv .venv
  fi

  # 统一使用虚拟环境内的 Python，避免系统 Python 和依赖版本漂移。
  if [ "${INSTALL_BACKEND_DEPS}" = "always" ] || { [ "${INSTALL_BACKEND_DEPS}" = "auto" ] && [ ! -x ".venv/bin/uvicorn" ]; }; then
    log "Installing backend dependencies"
    ./.venv/bin/python -m pip install -r requirements.txt
  fi
}

prepare_frontend_env() {
  cd "${ROOT_DIR}/frontend"
  require_command npm

  if [ "${INSTALL_FRONTEND_DEPS}" = "always" ] || { [ "${INSTALL_FRONTEND_DEPS}" = "auto" ] && [ ! -d "node_modules" ]; }; then
    if [ -f "package-lock.json" ]; then
      log "Installing frontend dependencies with npm ci"
      npm ci
    else
      log "Installing frontend dependencies with npm install"
      npm install
    fi
  fi
}

start_backend() {
  local backend_log="${LOG_DIR}/backend.log"

  require_free_port "${BACKEND_PORT}" "Backend"
  prepare_backend_env

  log "Starting backend on http://${BACKEND_HOST}:${BACKEND_PORT}"
  APP_HOST="${BACKEND_HOST}" \
  APP_PORT="${BACKEND_PORT}" \
  FRONTEND_ORIGINS="${FRONTEND_ORIGINS}" \
  ./.venv/bin/python -m uvicorn src.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" \
    >"${backend_log}" 2>&1 &

  BACKEND_PID=$!
  STARTED_PIDS+=("${BACKEND_PID}")
  log "Backend PID ${BACKEND_PID}; log: ${backend_log}"
}

start_frontend() {
  local frontend_log="${LOG_DIR}/frontend.log"

  require_free_port "${FRONTEND_PORT}" "Frontend"
  prepare_frontend_env

  log "Starting frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  HOST="${FRONTEND_HOST}" \
  PORT="${FRONTEND_PORT}" \
  BACKEND_API_BASE_URL="${BACKEND_API_BASE_URL}" \
  npm run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" \
    >"${frontend_log}" 2>&1 &

  FRONTEND_PID=$!
  STARTED_PIDS+=("${FRONTEND_PID}")
  log "Frontend PID ${FRONTEND_PID}; log: ${frontend_log}"
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local retries="${3:-60}"
  local delay_seconds="${4:-1}"
  local pid="${5:-}"
  local log_file="${6:-}"
  local attempt

  if ! command -v curl >/dev/null 2>&1; then
    log "curl is unavailable; skipping ${label} readiness check"
    return 0
  fi

  for attempt in $(seq 1 "${retries}"); do
    # 等待健康检查时同步确认服务进程仍存活，避免失败后空等。
    if [ -n "${pid}" ] && ! kill -0 "${pid}" 2>/dev/null; then
      if [ -n "${log_file}" ] && [ -f "${log_file}" ]; then
        log "${label} exited before it became ready. Recent log:"
        tail -n 40 "${log_file}" || true
      fi
      fail "${label} process exited before readiness check passed"
    fi

    if curl -fsS "${url}" >/dev/null 2>&1; then
      log "${label} is ready: ${url}"
      return 0
    fi
    sleep "${delay_seconds}"
  done

  fail "${label} did not become ready: ${url}"
}

cleanup() {
  local pid

  STOPPING=1
  if [ "${#STARTED_PIDS[@]}" -eq 0 ]; then
    return 0
  fi

  for pid in "${STARTED_PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done
}

monitor_processes() {
  local pid

  log "Press Ctrl+C to stop HydroAgent services"
  while :; do
    if [ "${STOPPING}" = "1" ]; then
      return 0
    fi

    for pid in "${STARTED_PIDS[@]}"; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        wait "${pid}" || fail "Service process ${pid} exited. Check logs in ${LOG_DIR}"
        return 0
      fi
    done
    sleep 1
  done
}

main() {
  require_mode

  if [ "${MODE}" = "-h" ] || [ "${MODE}" = "--help" ]; then
    usage
    exit 0
  fi

  validate_install_policy "${INSTALL_BACKEND_DEPS}" "INSTALL_BACKEND_DEPS"
  validate_install_policy "${INSTALL_FRONTEND_DEPS}" "INSTALL_FRONTEND_DEPS"
  prepare_log_dir

  case "${MODE}" in
    all)
      start_backend
      wait_for_http "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" "Backend" 60 1 "${BACKEND_PID}" "${LOG_DIR}/backend.log"
      start_frontend
      wait_for_http "http://${FRONTEND_HOST}:${FRONTEND_PORT}" "Frontend" 60 1 "${FRONTEND_PID}" "${LOG_DIR}/frontend.log"
      ;;
    backend)
      start_backend
      wait_for_http "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" "Backend" 60 1 "${BACKEND_PID}" "${LOG_DIR}/backend.log"
      ;;
    frontend)
      start_frontend
      wait_for_http "http://${FRONTEND_HOST}:${FRONTEND_PORT}" "Frontend" 60 1 "${FRONTEND_PID}" "${LOG_DIR}/frontend.log"
      ;;
  esac

  log "Backend API: ${BACKEND_API_BASE_URL}"
  log "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  monitor_processes
}

handle_exit() {
  cleanup
}

handle_signal() {
  printf "\n[HydroAgent] Stopping services...\n"
  cleanup
  exit 130
}

trap handle_exit EXIT
trap handle_signal INT TERM

main
