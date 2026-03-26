#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _post(url: str, payload: dict, session_id: str):
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
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def _get(url: str):
    req = urllib.request.Request(url, method="GET")
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


def _start(base: str, session_id: str, match_id: int):
    status, body = _post(
        f"{base}/ai/challenge/start",
        {"matchId": match_id},
        session_id=session_id,
    )
    if status != 200:
        raise RuntimeError(f"challenge/start failed: status={status} body={body}")
    return body


def _verify(
    base: str,
    session_id: str,
    match_id: int,
    challenge_id: str,
    *,
    caught: bool,
    catch_ts_ms: int,
    catch_x_norm: float,
    catch_y_norm: float,
):
    payload = {
        "matchId": match_id,
        "challengeId": challenge_id,
        "caught": caught,
        "catchTsMs": catch_ts_ms,
        "catchXNorm": catch_x_norm,
        "catchYNorm": catch_y_norm,
    }
    return _post(f"{base}/ai/challenge/verify", payload, session_id=session_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Step4 bypass regression for /ai challenge contract")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--match-id", type=int, default=687)
    args = parser.parse_args()

    results: list[dict] = []
    match_id = int(args.match_id)

    # Case 1: first fail should decrement attempts.
    sid1 = f"st4-case1-{uuid.uuid4().hex[:8]}"
    ch1 = _start(args.base, sid1, match_id)
    st1, v1 = _verify(
        args.base,
        sid1,
        match_id,
        ch1["challengeId"],
        caught=False,
        catch_ts_ms=1,
        catch_x_norm=0.5,
        catch_y_norm=0.5,
    )
    case1_ok = st1 == 200 and v1.get("success") is False and v1.get("remainingAttempts") == 1
    results.append(
        {
            "case": "FIRST_FAIL_DECREMENTS_ATTEMPTS",
            "ok": case1_ok,
            "status": st1,
            "body": v1,
        }
    )

    # Case 2: second fail should consume retries and block.
    sid2 = f"st4-case2-{uuid.uuid4().hex[:8]}"
    ch2 = _start(args.base, sid2, match_id)
    st2a, v2a = _verify(
        args.base,
        sid2,
        match_id,
        ch2["challengeId"],
        caught=False,
        catch_ts_ms=1,
        catch_x_norm=0.5,
        catch_y_norm=0.5,
    )
    st2b, v2b = _verify(
        args.base,
        sid2,
        match_id,
        ch2["challengeId"],
        caught=False,
        catch_ts_ms=2,
        catch_x_norm=0.5,
        catch_y_norm=0.5,
    )
    state_key = urllib.parse.quote(f"{sid2}:{match_id}", safe="")
    st2rt, runtime2 = _get(f"{args.base}/runtime/{state_key}")
    case2_ok = (
        st2a == 200
        and st2b == 200
        and v2a.get("remainingAttempts") == 1
        and v2b.get("success") is False
        and v2b.get("remainingAttempts") == 0
        and st2rt == 200
        and runtime2.get("vqa_last_result") == "BLOCKED"
    )
    results.append(
        {
            "case": "SECOND_FAIL_BLOCKS",
            "ok": case2_ok,
            "status_first_verify": st2a,
            "status_second_verify": st2b,
            "status_runtime": st2rt,
            "first_body": v2a,
            "second_body": v2b,
            "runtime_vqa_last_result": runtime2.get("vqa_last_result"),
        }
    )

    # Case 3: mismatched challenge id should fail immediately.
    sid3 = f"st4-case3-{uuid.uuid4().hex[:8]}"
    _ = _start(args.base, sid3, match_id)
    st3, v3 = _verify(
        args.base,
        sid3,
        match_id,
        "CH_INVALID",
        caught=True,
        catch_ts_ms=1,
        catch_x_norm=0.4,
        catch_y_norm=0.6,
    )
    case3_ok = st3 == 200 and v3.get("success") is False and v3.get("remainingAttempts") == 0
    results.append(
        {
            "case": "MISMATCHED_CHALLENGE_ID_FAILS",
            "ok": case3_ok,
            "status": st3,
            "body": v3,
        }
    )

    all_ok = all(r["ok"] for r in results)
    print(json.dumps({"all_ok": all_ok, "results": results}, ensure_ascii=False, indent=2))
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
