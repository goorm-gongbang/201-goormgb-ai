#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"
FRONTEND_URL="${TM_FRONTEND_URL:-http://localhost:3000}"

echo "[st4-2] checking pilot stack health"
cd "${PILOT_DIR}"
./pilot_check.sh

echo "[st4-2] checking frontend availability: ${FRONTEND_URL}"
curl -fsS "${FRONTEND_URL}/games/game-001" >/dev/null 2>&1 || {
  echo "[st4-2] frontend is not reachable at ${FRONTEND_URL}"
  echo "[st4-2] tip: start FE with Envoy rewrite"
  echo "  cd ${ROOT_DIR}/platform/frontend && TM_API_PROXY_TARGET=http://localhost:10000 npm run dev"
  exit 1
}

echo "[st4-2] running attack-agent MAP flow (challenge pass)"
cd "${ROOT_DIR}"
PRE_LOG_TS="$(date +%s)"
RUN_OUTPUT="$(
  python -m traffic_master_ai.attack.a1_mvp.main \
    --mode MAP \
    --frontend-url "${FRONTEND_URL}" \
    --headless \
    --challenge-mode pass \
    --challenge-strategy api_fast
)"
echo "${RUN_OUTPUT}"

ATTACK_LOG_PATH="$(echo "${RUN_OUTPUT}" | sed -n 's/.*log=\(logs\/attack_mvp\/[^ ]*\.jsonl\).*/\1/p' | tail -n 1)"
if [[ -z "${ATTACK_LOG_PATH}" ]]; then
  echo "[st4-2] failed to parse attack log path from output"
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/${ATTACK_LOG_PATH}" ]]; then
  echo "[st4-2] attack log file not found: ${ROOT_DIR}/${ATTACK_LOG_PATH}"
  exit 1
fi

echo "[st4-2] validating attack log: ${ATTACK_LOG_PATH}"
python - <<PY
import json
from pathlib import Path

log_path = Path("${ROOT_DIR}/${ATTACK_LOG_PATH}")
events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

required = {
    "ENTRY_CLICKED",
    "QUEUE_PASSED",
    "CHALLENGE_PASSED",
    "HOLD_ACQUIRED",
    "PAYMENT_COMPLETED",
    "RUN_END",
}
present = {e.get("event") for e in events}
missing = sorted(required - present)
if missing:
    raise SystemExit(f"[st4-2] missing required events: {missing}")

terminal = next((e for e in reversed(events) if e.get("event") == "RUN_END"), None)
if terminal is None or terminal.get("terminal_reason") != "DONE":
    raise SystemExit(f"[st4-2] terminal reason is not DONE: {terminal}")

print("[st4-2] attack flow validation passed")
print(
    json.dumps(
        {
            "terminal_reason": terminal.get("terminal_reason"),
            "log_path": str(log_path),
        },
        ensure_ascii=False,
    )
)
PY

echo "[st4-2] checking ext_authz traffic in adapter logs"
ADAPTER_LOGS="$(docker logs --since "${PRE_LOG_TS}" istio_adapter_local-authz-adapter-1 2>&1 || true)"
echo "${ADAPTER_LOGS}" | rg -q "/check/api/holds" || {
  echo "[st4-2] ext_authz check missing /check/api/holds in adapter logs"
  exit 1
}
echo "${ADAPTER_LOGS}" | rg -q "/check/api/payments" || {
  echo "[st4-2] ext_authz check missing /check/api/payments in adapter logs"
  exit 1
}

echo "[st4-2] success: Envoy/ext_authz path + attack MAP flow DONE verified"
