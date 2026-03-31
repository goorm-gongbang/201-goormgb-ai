#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="$ROOT_DIR/pilot/istio_adapter_local"

echo "[step4-all] starting ST4 chain in $ROOT_DIR"

echo "[step4-all] ST4-2: e2e flow + ext_authz checks"
"$PILOT_DIR/pilot_step4_st2_e2e.sh"

echo "[step4-all] ST4-3: bypass + metrics quality gate"
"$PILOT_DIR/pilot_step4_st3_metrics.sh"

echo "[step4-all] ST4-4: standalone bypass regression"
cd "$ROOT_DIR"
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
python scripts/step4_bypass_regression.py

echo "[step4-all] success"
