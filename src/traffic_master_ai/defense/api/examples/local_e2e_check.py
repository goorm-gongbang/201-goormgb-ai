"""Local E2E check for defense runtime API without Istio/adapter."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import random
import urllib.error
import urllib.request
from typing import Any


def _post(base: str, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{path}",
        data=raw,
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get(base: str, path: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(f"{base}{path}", method="GET")
    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _derive_hidden(
    *,
    secret: str,
    session_id: str,
    challenge_id: str,
    challenge_type: str,
    issued_at_ms: int,
) -> tuple[float, float, int]:
    seed_src = f"{session_id}:{challenge_id}:{challenge_type}:{issued_at_ms}"
    digest = hmac.new(secret.encode("utf-8"), seed_src.encode("utf-8"), hashlib.sha256).digest()
    rng = random.Random(int.from_bytes(digest[:8], byteorder="big", signed=False))
    target_x = round(rng.uniform(220.0, 580.0), 2)
    target_y = round(rng.uniform(120.0, 330.0), 2)
    timing_target_ms = rng.randint(920, 1360)
    return target_x, target_y, timing_target_ms


def _make_pass_events(target_x: float, target_y: float, click_t_ms: int) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    start_x = target_x - 120.0
    start_y = target_y + 90.0
    points.append({"t_ms": 0, "x": start_x, "y": start_y, "event": "down"})
    steps = 32
    for idx in range(1, steps + 1):
        ratio = idx / steps
        t_ms = int(20 * idx)
        x = start_x + (target_x - start_x) * ratio
        y = start_y + (target_y - start_y) * ratio
        points.append({"t_ms": t_ms, "x": round(x, 2), "y": round(y, 2), "event": "move"})
    points.append({"t_ms": click_t_ms, "x": target_x, "y": target_y, "event": "click"})
    return points


def main() -> int:
    parser = argparse.ArgumentParser(description="Local defense API E2E checker")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--session-id", default="sess-local-e2e", help="Session id")
    parser.add_argument(
        "--mode",
        default="pass",
        choices=["pass", "block"],
        help="pass: solve challenge, block: fail until blocked",
    )
    parser.add_argument(
        "--challenge-secret",
        default="tm-local-dev-secret",
        help="Server challenge secret (required for pass mode)",
    )
    args = parser.parse_args()

    status, body = _post(
        args.base,
        "/evaluate",
        {
            "session_id": args.session_id,
            "path": "/api/holds",
            "method": "POST",
            "timestamp": 1772500000000,
            "flow_state": "S4",
        },
    )
    print("evaluate ->", status, body.get("action"), body.get("reason"))
    if status != 200 or body.get("action") != "CHALLENGE":
        return 1

    status, start_body = _post(
        args.base,
        "/challenge/start",
        {"session_id": args.session_id, "flow_state": "S3", "challenge_type": "catch_ball"},
    )
    print("challenge/start ->", status)
    if status != 200:
        return 1

    challenge_id = start_body["challenge_id"]
    challenge_token = start_body["challenge_token"]

    if args.mode == "pass":
        target_x, target_y, timing_target_ms = _derive_hidden(
            secret=args.challenge_secret,
            session_id=args.session_id,
            challenge_id=challenge_id,
            challenge_type=start_body["challenge_type"],
            issued_at_ms=start_body["issued_at_ms"],
        )
        events = _make_pass_events(target_x, target_y, timing_target_ms)
        status, ingest_body = _post(
            args.base,
            "/challenge/event",
            {
                "session_id": args.session_id,
                "challenge_id": challenge_id,
                "challenge_token": challenge_token,
                "events": events,
            },
        )
        print("challenge/event ->", status, ingest_body.get("accepted_events"))
        if status != 200:
            return 1
        status, verify_body = _post(
            args.base,
            "/challenge/verify",
            {
                "session_id": args.session_id,
                "challenge_id": challenge_id,
                "challenge_token": challenge_token,
                "final_click_ts_ms": timing_target_ms,
            },
        )
        print("challenge/verify ->", status, verify_body.get("result"))
        if status != 200 or verify_body.get("result") != "PASSED":
            return 1
    else:
        # intentionally insufficient events -> failed then blocked
        status, _ = _post(
            args.base,
            "/challenge/event",
            {
                "session_id": args.session_id,
                "challenge_id": challenge_id,
                "challenge_token": challenge_token,
                "events": [
                    {"t_ms": 0, "x": 10, "y": 10, "event": "down"},
                    {"t_ms": 10, "x": 20, "y": 20, "event": "click"},
                ],
            },
        )
        if status != 200:
            return 1
        for idx in range(2):
            status, verify_body = _post(
                args.base,
                "/challenge/verify",
                {
                    "session_id": args.session_id,
                    "challenge_id": challenge_id,
                    "challenge_token": challenge_token,
                },
            )
            print("challenge/verify attempt", idx + 1, "->", status, verify_body.get("result"))
            if status != 200:
                return 1

    status, runtime_body = _get(args.base, f"/runtime/{args.session_id}")
    print("runtime ->", status, runtime_body.get("flow_state"), runtime_body.get("defense_tier"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
