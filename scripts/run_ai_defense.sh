#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${TM_AI_ENV_FILE:-${ROOT_DIR}/.env.ai}"
HOST="${TM_AI_DEFENSE_HOST:-0.0.0.0}"
PORT="${TM_AI_DEFENSE_PORT:-8000}"

if [[ -f "${ENV_FILE}" ]]; then
  echo "[run_ai_defense] loading env file: ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "[run_ai_defense] env file not found, skipping: ${ENV_FILE}"
fi

if [[ ! -f "${ROOT_DIR}/.venv/bin/activate" ]]; then
  echo "[run_ai_defense] missing virtualenv: ${ROOT_DIR}/.venv"
  echo "Create it first and install dependencies."
  exit 1
fi

source "${ROOT_DIR}/.venv/bin/activate"
exec python -m uvicorn traffic_master_ai.defense.api.main:app --host "${HOST}" --port "${PORT}" --reload
