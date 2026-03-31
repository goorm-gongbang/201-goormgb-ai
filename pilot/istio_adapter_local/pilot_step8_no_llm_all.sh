#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"
FRONTEND_URL="${TM_FRONTEND_URL:-http://localhost:3000}"
RUN_ATTACK_EXECUTE="${TM_STEP8_RUN_ATTACK_EXECUTE:-0}"

echo "[step8-no-llm] start"

echo "[step8-no-llm] 1) ensure pilot stack and ST4 chain"
cd "${PILOT_DIR}"
./pilot_step4_all.sh

echo "[step8-no-llm] 2) run Step5 offline no-key chain"
cd "${ROOT_DIR}"
./scripts/step5_no_key_all.sh

echo "[step8-no-llm] 3) run Step7 attack matrix (non-LLM)"
if [[ "${RUN_ATTACK_EXECUTE}" == "1" ]]; then
  python scripts/step7_attack_mode_matrix.py --frontend-url "${FRONTEND_URL}" --execute
else
  python scripts/step7_attack_mode_matrix.py --frontend-url "${FRONTEND_URL}"
fi

echo "[step8-no-llm] done"
echo "[step8-no-llm] outputs:"
echo "  - logs/step4/st4_3_metrics_report.json"
echo "  - logs/step5_batch_eval_summary.json"
echo "  - logs/step5_policy_apply_decision.json"
echo "  - logs/step7_attack_matrix_summary.json"
