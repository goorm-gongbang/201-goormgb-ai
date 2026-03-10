#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${ROOT_DIR}/pilot/istio_adapter_local"

echo "[step3] starting local pilot stack"
cd "${PILOT_DIR}"
./pilot_down.sh || true
./pilot_up.sh
./pilot_check.sh

echo "[step3] scenario A: user flow (challenge -> verify pass -> booking entry allow)"
python - <<'PY'
import json
import urllib.error
import urllib.request
import uuid

ENVOY = "http://localhost:10000"
AI = "http://localhost:8000"
sid = "sess-step3-user-" + uuid.uuid4().hex[:8]

def post(url: str, payload: dict, headers: dict | None = None):
    h = {"content-type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=h
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8")
            return r.status, body, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)

def get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status, r.read().decode("utf-8"), dict(r.headers)

# 1) High-value booking entry should require challenge first.
s1, b1, h1 = post(
    f"{ENVOY}/api/booking/entry",
    {"sessionId": sid, "gameId": "game-001"},
    {"x-session-id": sid, "x-trace-id": "trc-step3-a-1", "x-flow-state": "S1"},
)
if s1 != 428:
    raise SystemExit(f"[step3][user] expected 428 before challenge, got {s1}: {b1}")

# 2) Backend challenge issue.
s2, b2, _ = get(f"{ENVOY}/api/security/challenge?sessionId={sid}", {"x-session-id": sid})
if s2 != 200:
    raise SystemExit(f"[step3][user] challenge issue failed: {s2} {b2}")
challenge = json.loads(b2)

# 3) Backend verify pass with telemetry.
telemetry = {
    "position_ok": True,
    "timing_ok": True,
    "distance_to_target": 10.0,
    "position": {"catch_radius": 38.0},
    "timing": {"indicator_enter_ts": 1000, "indicator_exit_ts": 1400, "click_ts": 1200},
    "drag": {
        "total_distance": 120.0,
        "linear_distance": 80.0,
        "curvature": 1.5,
        "drag_path": [
            {"x": 10, "y": 10, "t": 10},
            {"x": 20, "y": 16, "t": 40},
            {"x": 32, "y": 23, "t": 70},
            {"x": 46, "y": 31, "t": 100},
            {"x": 58, "y": 38, "t": 130},
        ],
    },
}
s3, b3, _ = post(
    f"{ENVOY}/api/security/verify",
    {
        "challengeId": challenge["challengeId"],
        "answer": "__VQA_PASS__",
        "sessionId": sid,
        "challengeToken": challenge["challengeToken"],
        "telemetry": telemetry,
    },
    {"x-session-id": sid},
)
if s3 != 200:
    raise SystemExit(f"[step3][user] challenge verify failed: {s3} {b3}")
verify = json.loads(b3)
if verify.get("result") != "PASS":
    raise SystemExit(f"[step3][user] expected PASS, got: {verify}")

# 4) Retry booking entry must now be allowed.
s4, b4, _ = post(
    f"{ENVOY}/api/booking/entry",
    {"sessionId": sid, "gameId": "game-001"},
    {"x-session-id": sid, "x-trace-id": "trc-step3-a-2", "x-flow-state": "S1"},
)
if s4 != 200:
    raise SystemExit(f"[step3][user] expected 200 after verify, got {s4}: {b4}")

# 5) AI runtime should be synced as vqa_passed=true.
s5, b5, _ = get(f"{AI}/runtime/{sid}")
runtime = json.loads(b5) if s5 == 200 else {}
if s5 != 200 or runtime.get("vqa_passed") is not True:
    raise SystemExit(f"[step3][user] runtime sync failed: {s5} {b5}")

print("[step3][user] ok:", json.dumps({
    "session_id": sid,
    "first_entry": s1,
    "verify_result": verify.get("result"),
    "retry_entry": s4,
    "runtime_vqa_passed": runtime.get("vqa_passed"),
}, ensure_ascii=False))
PY

echo "[step3] scenario B: attacker-like failure path (no VQA solver)"
python -m traffic_master_ai.defense.api.examples.local_e2e_check \
  --base http://127.0.0.1:8000 \
  --session-id "sess-step3-attack-sim" \
  --mode block

echo "[step3] scenario C (optional): real attack agent run (requires playwright)"
python - <<'PY'
import importlib.util
import subprocess
import sys

if importlib.util.find_spec("playwright") is None:
    print("[step3][attack-agent] skipped: playwright is not installed in current python env")
    raise SystemExit(0)

cmd = [
    sys.executable,
    "-m",
    "traffic_master_ai.attack.a1_mvp.main",
    "--mode",
    "MAP",
    "--frontend-url",
    "http://localhost:3000",
    "--headless",
    "--mouse-profile",
    "bot",
]
print("[step3][attack-agent] running:", " ".join(cmd))
proc = subprocess.run(cmd, check=False)
print("[step3][attack-agent] exit:", proc.returncode)
raise SystemExit(proc.returncode)
PY

echo "[step3] done"
echo "[step3] stack is still running. stop with:"
echo "  cd ${PILOT_DIR} && ./pilot_down.sh"
