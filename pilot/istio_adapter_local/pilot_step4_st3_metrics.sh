#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${ROOT_DIR}/logs/step4"
OUT_FILE="${OUT_DIR}/st4_3_metrics_report.json"

mkdir -p "${OUT_DIR}"

echo "[st4-3] running bypass regression against AI runtime"
python "${ROOT_DIR}/scripts/step4_bypass_regression.py" --base http://127.0.0.1:8000

echo "[st4-3] running metrics quality gate (strict)"
python "${ROOT_DIR}/scripts/step4_metrics_report.py" \
  --attack-log-dir "${ROOT_DIR}/logs/attack_mvp" \
  --decision-log "${ROOT_DIR}/logs/defense_decision_audit.jsonl" \
  --latest-n 30 \
  --strict \
  --output "${OUT_FILE}"

echo "[st4-3] success: ${OUT_FILE}"
