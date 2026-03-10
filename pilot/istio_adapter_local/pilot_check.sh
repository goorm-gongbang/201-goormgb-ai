#!/usr/bin/env bash
set -euo pipefail

wait_http_ok() {
  local url="$1"
  local max_tries="${2:-40}"
  local sleep_sec="${3:-1}"
  local i=1
  while [[ $i -le $max_tries ]]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_sec"
    i=$((i + 1))
  done
  return 1
}

wait_http_code() {
  local url="$1"
  local expected="$2"
  local max_tries="${3:-40}"
  local sleep_sec="${4:-1}"
  local i=1
  while [[ $i -le $max_tries ]]; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)
    if [[ "$code" == "$expected" ]]; then
      return 0
    fi
    sleep "$sleep_sec"
    i=$((i + 1))
  done
  return 1
}

wait_http_ok http://localhost:8000/healthz || { echo "[tm-pilot-check] ai-defense health failed"; exit 1; }
wait_http_ok http://localhost:9001/healthz || { echo "[tm-pilot-check] authz-adapter health failed"; exit 1; }
wait_http_ok http://localhost:9901/server_info || { echo "[tm-pilot-check] envoy admin health failed"; exit 1; }
# backend may take longer than containers, wait until route is alive.
wait_http_code http://localhost:10000/api/games/game-001 200 || {
  echo "[tm-pilot-check] backend route not ready via envoy";
  exit 1;
}

# ext_authz + backend path check
HTTP_CODE=$(curl -s -o /tmp/tm_pilot_check_body.json -w "%{http_code}" \
  -H 'x-session-id:sess-pilot-check' \
  -H 'x-trace-id:trc-pilot-check-1' \
  -H 'x-flow-state:S2' \
  -H 'content-type:application/json' \
  -X POST http://localhost:10000/api/queue/enter \
  -d '{"sessionId":"sess-pilot-check","gameId":"game-001","mode":"RECOMMEND"}')

echo "[tm-pilot-check] envoy response code: ${HTTP_CODE}"
cat /tmp/tm_pilot_check_body.json

if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "403" && "${HTTP_CODE}" != "428" ]]; then
  echo "[tm-pilot-check] unexpected code (expected one of 200/403/428)"
  exit 1
fi
