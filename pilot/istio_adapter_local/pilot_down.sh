#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"
BACKEND_PID_FILE="${PILOT_DIR}/.backend.pid"
FRONTEND_PID_FILE="${PILOT_DIR}/.frontend.pid"

if [[ -f "${BACKEND_PID_FILE}" ]]; then
  kill "$(cat "${BACKEND_PID_FILE}")" 2>/dev/null || true
  rm -f "${BACKEND_PID_FILE}"
fi
if [[ -f "${FRONTEND_PID_FILE}" ]]; then
  kill "$(cat "${FRONTEND_PID_FILE}")" 2>/dev/null || true
  rm -f "${FRONTEND_PID_FILE}"
fi

pkill -f "trafficmaster.*jar" 2>/dev/null || true
pkill -f "platform/backend.*bootRun" 2>/dev/null || true
pkill -f "platform/frontend.*next dev" 2>/dev/null || true

cd "${PILOT_DIR}"
docker-compose down

echo "[tm-pilot] stopped"
