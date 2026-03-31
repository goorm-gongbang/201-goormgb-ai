#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"
BACKEND_PID_FILE="${PILOT_DIR}/.backend.pid"
FRONTEND_PID_FILE="${PILOT_DIR}/.frontend.pid"

kill_pid_file_process() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${pid_file}"
  fi
}

kill_port_listener() {
  local port="$1"
  local pids
  pids="$(lsof -t -iTCP:${port} -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "[tm-pilot] cleaning listener(s) on :${port} -> ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local retries="${3:-30}"
  for _ in $(seq 1 "${retries}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "[tm-pilot] ${name} ready: ${url}"
      return 0
    fi
    sleep 1
  done
  echo "[tm-pilot] ${name} not ready: ${url}"
  return 1
}

# Cleanup stale host processes before startup.
kill_pid_file_process "${BACKEND_PID_FILE}"
kill_pid_file_process "${FRONTEND_PID_FILE}"
kill_port_listener 8080
kill_port_listener 3000

cd "${ROOT_DIR}/platform/backend"
./gradlew bootJar --console=plain >/tmp/tm_backend_build.log 2>&1
BACKEND_JAR="$(ls -1t build/libs/*.jar | head -n 1)"
nohup java -jar "${BACKEND_JAR}" >/tmp/tm_backend.log 2>&1 &
BACKEND_PID=$!
echo "${BACKEND_PID}" >"${BACKEND_PID_FILE}"
if ! wait_for_http "http://localhost:8080/api/games/game-001" "backend" 45; then
  echo "[tm-pilot] backend failed to start. tail /tmp/tm_backend.log:"
  tail -n 120 /tmp/tm_backend.log || true
  exit 1
fi

cd "${PILOT_DIR}"
docker-compose up -d --build

cd "${ROOT_DIR}/platform/frontend"
nohup env TM_API_PROXY_TARGET=http://localhost:10000 npm run dev >/tmp/tm_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "${FRONTEND_PID}" >"${FRONTEND_PID_FILE}"
if ! wait_for_http "http://localhost:3000" "frontend" 60; then
  echo "[tm-pilot] frontend failed to start. tail /tmp/tm_frontend.log:"
  tail -n 120 /tmp/tm_frontend.log || true
  exit 1
fi

cat <<MSG
[tm-pilot] started
- backend pid: ${BACKEND_PID} (log: /tmp/tm_backend.log)
- frontend pid: ${FRONTEND_PID} (log: /tmp/tm_frontend.log)
- envoy: http://localhost:10000
- frontend: http://localhost:3000

stop:
  cd ${PILOT_DIR} && ./pilot_down.sh
MSG
