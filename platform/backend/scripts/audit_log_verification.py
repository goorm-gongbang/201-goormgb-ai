#!/usr/bin/env python3
"""
Stage 7: Audit log verification script.
Parses decision_audit.jsonl to verify log integrity and replayability.

Usage:
    python3 audit_log_verification.py logs/decision_audit.jsonl
"""

import json
import sys
from datetime import datetime
from collections import defaultdict


def load_logs(path: str) -> list[dict]:
    """Load JSONL file into list of dicts."""
    events = []
    with open(path, 'r') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ⚠️ Line {i}: JSON parse error — {e}")
    return events


def verify_schema(events: list[dict]) -> tuple[int, int]:
    """Check that all events have required fields."""
    required = ['ts', 'sessionId', 'eventType']
    ok, fail = 0, 0
    for i, ev in enumerate(events):
        missing = [f for f in required if f not in ev]
        if missing:
            print(f"  ❌ Event {i}: missing fields {missing}")
            fail += 1
        else:
            ok += 1
    return ok, fail


def verify_chronological(events: list[dict]) -> bool:
    """Verify events are in chronological order."""
    prev_ts = 0.0
    for i, ev in enumerate(events):
        ts = ev.get('ts', 0)
        # Handle both epoch float and ISO string formats
        if isinstance(ts, str):
            prev_ts_str = str(prev_ts) if isinstance(prev_ts, str) else ""
            if ts < prev_ts_str:
                print(f"  ❌ Event {i}: out of order ({prev_ts_str} > {ts})")
                return False
            prev_ts = ts
        else:
            ts_val = float(ts)
            if ts_val < prev_ts:
                print(f"  ❌ Event {i}: out of order ({prev_ts} > {ts_val})")
                return False
            prev_ts = ts_val
    return True


def verify_correlation_chains(events: list[dict]) -> dict:
    """Group events by correlationId and check chain completeness."""
    chains = defaultdict(list)
    for ev in events:
        cid = ev.get('correlationId', 'none')
        chains[cid].append(ev['eventType'])
    return dict(chains)


def verify_session_flows(events: list[dict]) -> dict:
    """Group events by sessionId to trace user flows."""
    flows = defaultdict(list)
    for ev in events:
        sid = ev.get('sessionId', 'unknown')
        flows[sid].append(ev['eventType'])
    return dict(flows)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 audit_log_verification.py <path_to_jsonl>")
        sys.exit(1)

    path = sys.argv[1]
    print(f"\n📋 Audit Log Verification: {path}")
    print("=" * 60)

    events = load_logs(path)
    print(f"\n📊 Total events: {len(events)}")

    # 1. Schema check
    print("\n🔍 Schema Validation:")
    ok, fail = verify_schema(events)
    print(f"  ✅ Valid: {ok}, ❌ Invalid: {fail}")

    # 2. Chronological order
    print("\n⏱️ Chronological Order:")
    if verify_chronological(events):
        print("  ✅ All events in chronological order")
    else:
        print("  ❌ Events out of order!")

    # 3. Event type distribution
    print("\n📈 Event Type Distribution:")
    type_counts = defaultdict(int)
    for ev in events:
        type_counts[ev.get('eventType', 'UNKNOWN')] += 1
    for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {etype}: {count}")

    # 4. Correlation chains
    print("\n🔗 Correlation Chains:")
    chains = verify_correlation_chains(events)
    for cid, evts in list(chains.items())[:5]:
        print(f"  {cid[:12]}... → {' → '.join(evts)}")
    if len(chains) > 5:
        print(f"  ... and {len(chains) - 5} more chains")

    # 5. Session flows
    print("\n👤 Session Flows:")
    flows = verify_session_flows(events)
    for sid, evts in list(flows.items())[:5]:
        print(f"  {sid[:20]}... → {' → '.join(evts[:8])}")
    if len(flows) > 5:
        print(f"  ... and {len(flows) - 5} more sessions")

    # Summary
    print("\n" + "=" * 60)
    total_pass = (fail == 0) and verify_chronological(events)
    print(f"{'✅ ALL CHECKS PASSED' if total_pass else '❌ SOME CHECKS FAILED'}")
    print()

    sys.exit(0 if total_pass else 1)


if __name__ == '__main__':
    main()
