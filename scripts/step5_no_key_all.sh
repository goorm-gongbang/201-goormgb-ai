#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[step5-no-key] build replay dataset"
python scripts/step5_build_replay_dataset.py \
  --decision-log logs/defense_decision_audit.jsonl \
  --replay-out logs/step5_replay_dataset.jsonl \
  --manifest-out logs/step5_replay_manifest.json \
  --min-decisions-per-session 1 \
  --min-suspicious-sessions 1 \
  --min-human-sessions 1 \
  --min-uncertain-sessions 0 \
  --max-sessions 200

echo "[step5-no-key] run offline batch evaluator (mock mode)"
python scripts/step5_batch_evaluator.py \
  --replay-log logs/step5_replay_dataset.jsonl \
  --manifest logs/step5_replay_manifest.json \
  --results-out logs/step5_offline_judge_results.jsonl \
  --patches-out logs/step5_offline_patch_candidates.json \
  --summary-out logs/step5_batch_eval_summary.json \
  --mode mock

echo "[step5-no-key] run policy guardrails (expect HOLD unless approval token configured)"
python scripts/step5_policy_guardrails.py \
  --batch-summary logs/step5_batch_eval_summary.json \
  --patches logs/step5_offline_patch_candidates.json \
  --decision-out logs/step5_policy_apply_decision.json

echo "[step5-no-key] done"
echo "[step5-no-key] outputs:"
echo "  - logs/step5_replay_dataset.jsonl"
echo "  - logs/step5_replay_manifest.json"
echo "  - logs/step5_batch_eval_summary.json"
echo "  - logs/step5_policy_apply_decision.json"
