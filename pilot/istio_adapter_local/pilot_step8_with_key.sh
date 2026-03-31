#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"
FRONTEND_URL="${TM_FRONTEND_URL:-http://localhost:3000}"
RUN_ATTACK_EXECUTE="${TM_STEP8_RUN_ATTACK_EXECUTE:-0}"
APPROVAL_TOKEN_INPUT="${1:-}"

if [[ -z "${TM_OFFLINE_LLM_API_KEY:-}" ]]; then
  echo "[step8-with-key] TM_OFFLINE_LLM_API_KEY is required"
  exit 1
fi

echo "[step8-with-key] start"

echo "[step8-with-key] 1) ensure pilot stack and ST4 chain"
cd "${PILOT_DIR}"
./pilot_step4_all.sh

echo "[step8-with-key] 2) run Step5 with LLM key"
cd "${ROOT_DIR}"
export TM_OFFLINE_LLM_MODE="openai_compatible"
./scripts/step5_with_key_all.sh "${APPROVAL_TOKEN_INPUT}"

echo "[step8-with-key] 3) run Step7 attack matrix"
if [[ "${RUN_ATTACK_EXECUTE}" == "1" ]]; then
  python scripts/step7_attack_mode_matrix.py --frontend-url "${FRONTEND_URL}" --execute
else
  python scripts/step7_attack_mode_matrix.py --frontend-url "${FRONTEND_URL}"
fi

echo "[step8-with-key] done"
