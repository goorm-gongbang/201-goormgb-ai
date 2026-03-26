#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _post(base: str, path: str, payload: dict, session_id: str) -> tuple[int, dict]:
    url = urllib.parse.urljoin(base, path)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-session-id": session_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return err.code, body


def _get(base: str, path: str) -> tuple[int, dict]:
    url = urllib.parse.urljoin(base, path)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return err.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Local /ai contract E2E smoke check")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--match-id", type=int, default=687)
    parser.add_argument("--session-id", default="")
    args = parser.parse_args()

    sid = args.session_id or f"ai-e2e-{uuid.uuid4().hex[:10]}"
    match_id = int(args.match_id)
    now_ms = int(time.time() * 1000)

    results: list[dict] = []

    precheck_status, precheck_body = _post(
        args.base,
        "/ai/precheck",
        {"matchId": match_id, "cfToken": "ok-local-dev"},
        sid,
    )
    results.append(
        {
            "step": "precheck",
            "ok": precheck_status == 200 and precheck_body.get("allowed") is True,
            "status": precheck_status,
            "body": precheck_body,
        }
    )

    telemetry_status, telemetry_body = _post(
        args.base,
        "/ai/telemetry/ingest",
        {
            "matchId": match_id,
            "stage": "QUEUE_ENTER_PRECLICK",
            "events": [
                {"type": "mousemove", "tsMs": now_ms - 120, "xNorm": 0.42, "yNorm": 0.72},
                {"type": "mousemove", "tsMs": now_ms - 80, "xNorm": 0.47, "yNorm": 0.76},
                {"type": "click", "tsMs": now_ms - 20, "xNorm": 0.51, "yNorm": 0.79, "button": 0},
            ],
        },
        sid,
    )
    results.append(
        {
            "step": "telemetry_ingest",
            "ok": telemetry_status == 200 and telemetry_body.get("accepted") is True,
            "status": telemetry_status,
            "body": telemetry_body,
        }
    )

    evaluate_status, evaluate_body = _post(
        args.base,
        "/ai/evaluate",
        {
            "event": {
                "eventType": "QUEUE_ENTER",
                "requestPath": f"/queue/matches/{match_id}/enter",
                "requestMethod": "POST",
            },
            "context": {"sid": sid},
        },
        sid,
    )
    queue_action = (evaluate_body.get("decision") or {}).get("action")
    results.append(
        {
            "step": "evaluate_queue_enter",
            "ok": evaluate_status == 200 and queue_action in {"NONE", "THROTTLE", "REQUIRE_S3", "BLOCK"},
            "status": evaluate_status,
            "action": queue_action,
            "body": evaluate_body,
        }
    )

    start_status, start_body = _post(
        args.base,
        "/ai/challenge/start",
        {"matchId": match_id},
        sid,
    )
    challenge_id = str(start_body.get("challengeId", ""))
    start_ok = (
        start_status == 200
        and bool(challenge_id)
        and isinstance(start_body.get("remainingAttempts"), int)
        and isinstance(start_body.get("expiresAtMs"), int)
    )
    results.append(
        {
            "step": "challenge_start",
            "ok": start_ok,
            "status": start_status,
            "body": start_body,
        }
    )

    verify_status, verify_body = _post(
        args.base,
        "/ai/challenge/verify",
        {
            "matchId": match_id,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": int(time.time() * 1000),
            "catchXNorm": 0.48,
            "catchYNorm": 0.54,
        },
        sid,
    )
    verify_ok = (
        verify_status == 200
        and verify_body.get("success") is True
        and isinstance(verify_body.get("remainingAttempts"), int)
    )
    results.append(
        {
            "step": "challenge_verify",
            "ok": verify_ok,
            "status": verify_status,
            "body": verify_body,
        }
    )

    state_key = urllib.parse.quote(f"{sid}:{match_id}", safe="")
    runtime_status, runtime_body = _get(args.base, f"/runtime/{state_key}")
    results.append(
        {
            "step": "runtime_snapshot",
            "ok": runtime_status == 200 and runtime_body.get("vqa_passed") is True,
            "status": runtime_status,
            "vqa_passed": runtime_body.get("vqa_passed"),
            "vqa_last_result": runtime_body.get("vqa_last_result"),
        }
    )

    all_ok = all(item["ok"] for item in results)
    print(
        json.dumps(
            {
                "all_ok": all_ok,
                "base": args.base,
                "session_id": sid,
                "match_id": match_id,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
