#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPROVAL_TOKEN_INPUT="${1:-}"

if [[ -z "${TM_OFFLINE_LLM_API_KEY:-}" ]]; then
  echo "[step5-with-key] TM_OFFLINE_LLM_API_KEY is required"
  exit 1
fi

cd "${ROOT_DIR}"
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[step5-with-key] build replay dataset"
python scripts/step5_build_replay_dataset.py \
  --decision-log logs/defense_decision_audit.jsonl \
  --replay-out logs/step5_replay_dataset.jsonl \
  --manifest-out logs/step5_replay_manifest.json \
  --min-decisions-per-session 1 \
  --min-suspicious-sessions 1 \
  --min-human-sessions 1 \
  --min-uncertain-sessions 0 \
  --max-sessions 200

echo "[step5-with-key] run batch evaluator (openai_compatible)"
python scripts/step5_batch_evaluator.py \
  --replay-log logs/step5_replay_dataset.jsonl \
  --manifest logs/step5_replay_manifest.json \
  --results-out logs/step5_offline_judge_results.jsonl \
  --patches-out logs/step5_offline_patch_candidates.json \
  --summary-out logs/step5_batch_eval_summary.json \
  --mode openai_compatible

echo "[step5-with-key] run policy guardrails"
python scripts/step5_policy_guardrails.py \
  --batch-summary logs/step5_batch_eval_summary.json \
  --patches logs/step5_offline_patch_candidates.json \
  --decision-out logs/step5_policy_apply_decision.json \
  --approval-token "${APPROVAL_TOKEN_INPUT}"

echo "[step5-with-key] done"
