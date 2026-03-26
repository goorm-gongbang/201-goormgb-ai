#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid


def _post(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def _start(base: str, session_id: str):
    status, body = _post(
        f"{base}/challenge/start",
        {"session_id": session_id, "flow_state": "S3", "challenge_type": "catch_ball"},
    )
    if status != 200:
        raise RuntimeError(f"challenge/start failed: status={status} body={body}")
    return body


def _verify(base: str, session_id: str, challenge_id: str, challenge_token: str, final_click_ts_ms: int | None = None):
    payload = {
        "session_id": session_id,
        "challenge_id": challenge_id,
        "challenge_token": challenge_token,
    }
    if final_click_ts_ms is not None:
        payload["final_click_ts_ms"] = final_click_ts_ms
    return _post(f"{base}/challenge/verify", payload)


def _ingest(base: str, session_id: str, challenge_id: str, challenge_token: str, events: list[dict]):
    return _post(
        f"{base}/challenge/event",
        {
            "session_id": session_id,
            "challenge_id": challenge_id,
            "challenge_token": challenge_token,
            "events": events,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Step4 bypass regression for challenge runtime")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    results: list[dict] = []

    # Case 1: no raw events -> must fail
    sid1 = f"st4-case1-{uuid.uuid4().hex[:8]}"
    ch1 = _start(args.base, sid1)
    st1, v1 = _verify(args.base, sid1, ch1["challenge_id"], ch1["challenge_token"])
    case1_ok = st1 == 200 and v1.get("passed") is False
    results.append(
        {
            "case": "NO_EVENTS_SHOULD_FAIL",
            "ok": case1_ok,
            "status": st1,
            "result": v1.get("result"),
            "reason": v1.get("reason"),
        }
    )

    # Case 2: impossible speed injection -> must fail (with enough events).
    sid2 = f"st4-case2-{uuid.uuid4().hex[:8]}"
    ch2 = _start(args.base, sid2)
    fast_events = [{"t_ms": 0, "x": 10, "y": 10, "event": "down"}]
    # Keep jump distance below TELEPORT threshold(220), but speed > max_speed(3.8 px/ms).
    # dt=1ms, dx=30px => speed=30 px/ms (impossible).
    x = 10
    y = 10
    for t in range(1, 29):
        x += 30
        y += 2
        fast_events.append({"t_ms": t, "x": x, "y": y, "event": "move"})
    fast_events.append({"t_ms": 29, "x": x, "y": y, "event": "click"})

    st2_ing, _ = _ingest(
        args.base,
        sid2,
        ch2["challenge_id"],
        ch2["challenge_token"],
        events=fast_events,
    )
    st2, v2 = _verify(args.base, sid2, ch2["challenge_id"], ch2["challenge_token"])
    case2_ok = st2_ing == 200 and st2 == 200 and v2.get("passed") is False
    results.append(
        {
            "case": "IMPOSSIBLE_SPEED_SHOULD_FAIL",
            "ok": case2_ok,
            "ingest_status": st2_ing,
            "status": st2,
            "result": v2.get("result"),
            "reason": v2.get("reason"),
        }
    )

    # Case 3: token/session binding mismatch -> must be rejected (400)
    sid3 = f"st4-case3-{uuid.uuid4().hex[:8]}"
    sid3_other = f"{sid3}-other"
    ch3 = _start(args.base, sid3)
    st3, v3 = _verify(args.base, sid3_other, ch3["challenge_id"], ch3["challenge_token"])
    case3_ok = st3 == 400
    results.append(
        {
            "case": "TOKEN_BINDING_MISMATCH_REJECTED",
            "ok": case3_ok,
            "status": st3,
            "detail": v3,
        }
    )

    all_ok = all(r["ok"] for r in results)
    print(json.dumps({"all_ok": all_ok, "results": results}, ensure_ascii=False, indent=2))
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
