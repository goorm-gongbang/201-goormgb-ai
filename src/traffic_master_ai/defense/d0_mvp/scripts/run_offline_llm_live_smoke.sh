#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/run_with_env.sh" python3 "$SCRIPT_DIR/offline_llm_live_smoke.py"
