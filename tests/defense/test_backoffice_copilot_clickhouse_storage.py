from __future__ import annotations

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage import (
    CanonicalAuditMappingError,
    DEFAULT_CLICKHOUSE_AUDIT_TABLE,
    ClickHouseAuditEventInsertRow,
    ClickHouseBatchWriteError,
    ClickHouseBatchWriteRequest,
    ClickHouseBatchWriteResult,
    ClickHouseBatchWriteRetryPolicy,
    ClickHouseWriteConfig,
    HttpClickHouseBatchWriteClient,
    build_clickhouse_audit_event_writer_repository,
    compute_clickhouse_raw_fact_dedup_key,
    get_clickhouse_audit_table_from_env,
    map_canonical_audit_payload_to_clickhouse_row,
    serialize_clickhouse_audit_event_insert_row,
    validate_clickhouse_audit_event_insert_row,
)
from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_repository import (
    ClickHouseAuditEventWriterRepository,
)
from traffic_master_ai.defense.backoffice_copilot.storage.validators import StorageValidationError


class _FakeClickHouseClient:
    def __init__(self, *, failures_before_success: int = 0) -> None:
        self.calls: list[tuple[str, list[dict[str, object]]]] = []
        self.failures_before_success = failures_before_success

    def execute(self, sql_text: str, rows: list[dict[str, object]]) -> None:
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise RuntimeError("clickhouse unavailable")
        self.calls.append((sql_text, rows))


class _RecordingClickHouseHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        self.__class__.requests.append(
            {
                "path": self.path,
                "query": parse_qs(urlsplit(self.path).query),
                "body": body,
                "authorization": self.headers.get("Authorization"),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover
        return


def _evaluate_row() -> ClickHouseAuditEventInsertRow:
    return ClickHouseAuditEventInsertRow(
        ts_ms=1000,
        session_id="sess-1",
        event_type="EVALUATE",
        trace_id="trace-1",
        flow_state="F4M",
        risk_tier="T2",
        action="THROTTLE",
        reason_code="RULE_HIT",
        policy_version="policy-v1",
        raw_payload_json='{"request_id":"req-1","decision_id":"dec-1"}',
    )


def _challenge_row() -> ClickHouseAuditEventInsertRow:
    return ClickHouseAuditEventInsertRow(
        ts_ms=1001,
        session_id="sess-1",
        event_type="CHALLENGE_VERIFIED",
        challenge_id="challenge-1",
        raw_payload_json='{"payload":{"result":"PASS"}}',
    )


class BackofficeCopilotClickHouseStorageTests(unittest.TestCase):
    def test_insert_row_contract_matches_task_2_minimum_columns(self) -> None:
        row = _evaluate_row()
        validated = validate_clickhouse_audit_event_insert_row(row)
        serialized = serialize_clickhouse_audit_event_insert_row(row)

        self.assertEqual(validated.session_id, "sess-1")
        self.assertEqual(
            tuple(serialized.keys()),
            (
                "ts_ms",
                "session_id",
                "event_type",
                "trace_id",
                "challenge_id",
                "flow_state",
                "risk_tier",
                "action",
                "reason_code",
                "policy_version",
                "raw_payload_json",
            ),
        )
        self.assertNotIn("match_id", serialized)
        self.assertNotIn("http_status", serialized)
        self.assertEqual(serialized["raw_payload_json"], '{"request_id":"req-1","decision_id":"dec-1"}')

    def test_insert_row_rejects_invalid_json_and_negative_ts(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_clickhouse_audit_event_insert_row(
                ClickHouseAuditEventInsertRow(
                    ts_ms=-1,
                    session_id="sess-1",
                    event_type="EVALUATE",
                    raw_payload_json="{}",
                )
            )

        with self.assertRaises(StorageValidationError):
            validate_clickhouse_audit_event_insert_row(
                ClickHouseAuditEventInsertRow(
                    ts_ms=1,
                    session_id="sess-1",
                    event_type="EVALUATE",
                    raw_payload_json="not-json",
                )
            )

    def test_repository_write_batch_uses_fixed_clickhouse_insert_surface(self) -> None:
        client = _FakeClickHouseClient()
        repository = build_clickhouse_audit_event_writer_repository(client)

        accepted_count = repository.write_batch([_evaluate_row(), _challenge_row()])

        self.assertEqual(accepted_count, 2)
        self.assertEqual(len(client.calls), 1)
        sql_text, rows = client.calls[0]
        self.assertEqual(
            sql_text,
            "INSERT INTO defense_audit_events (ts_ms, session_id, event_type, trace_id, challenge_id, flow_state, risk_tier, action, reason_code, policy_version, raw_payload_json) VALUES",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["risk_tier"], "T2")
        self.assertEqual(rows[1]["challenge_id"], "challenge-1")
        self.assertIsNone(rows[1]["trace_id"])

    def test_canonical_audit_mapping_normalizes_defense_tier_into_risk_tier(self) -> None:
        row = map_canonical_audit_payload_to_clickhouse_row(
            {
                "ts_ms": 1710000000000,
                "session_id": "sess-1",
                "trace_id": "trace-1",
                "event_type": "EVALUATE",
                "flow_state": "F4M",
                "defense_tier": "T2",
                "action": "THROTTLE",
                "reason_code": "RULE_HIT",
                "policy_version": "policy-v2",
                "extra_field": {"kept": True},
            }
        )

        self.assertEqual(row.risk_tier, "T2")
        self.assertEqual(row.trace_id, "trace-1")
        self.assertIn('"defense_tier":"T2"', row.raw_payload_json)
        self.assertIn('"extra_field":{"kept":true}', row.raw_payload_json)

    def test_canonical_audit_mapping_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(CanonicalAuditMappingError):
            map_canonical_audit_payload_to_clickhouse_row(
                {
                    "ts_ms": 1710000000000,
                    "event_type": "EVALUATE",
                }
            )

    def test_dedup_key_is_stable_for_identical_rows(self) -> None:
        row = map_canonical_audit_payload_to_clickhouse_row(
            {
                "ts_ms": 1710000000000,
                "session_id": "sess-1",
                "event_type": "CHALLENGE_VERIFIED",
                "challenge_id": "challenge-1",
                "payload": {"result": "PASS"},
            }
        )

        self.assertEqual(
            compute_clickhouse_raw_fact_dedup_key(row),
            compute_clickhouse_raw_fact_dedup_key(row),
        )

    def test_repository_write_batch_request_preserves_empty_batch_semantics(self) -> None:
        client = _FakeClickHouseClient()
        repository = ClickHouseAuditEventWriterRepository(
            client=client,
            config=ClickHouseWriteConfig(table_name="custom_defense_audit_events"),
        )

        result = repository.write_batch_request(ClickHouseBatchWriteRequest(rows=()))

        self.assertEqual(
            result,
            ClickHouseBatchWriteResult(
                table_name="custom_defense_audit_events",
                attempted_row_count=0,
                accepted_row_count=0,
            ),
        )
        self.assertEqual(client.calls, [])

    def test_repository_retries_then_succeeds_for_transient_clickhouse_failure(self) -> None:
        client = _FakeClickHouseClient(failures_before_success=1)
        repository = build_clickhouse_audit_event_writer_repository(client)

        result = repository.write_batch_request_with_retry(
            ClickHouseBatchWriteRequest(rows=(_evaluate_row(),)),
            retry_policy=ClickHouseBatchWriteRetryPolicy(max_attempts=2, backoff_ms=0),
        )

        self.assertEqual(result.accepted_row_count, 1)
        self.assertEqual(len(client.calls), 1)

    def test_repository_raises_typed_error_when_clickhouse_batch_exhausts_retry_budget(self) -> None:
        client = _FakeClickHouseClient(failures_before_success=2)
        repository = build_clickhouse_audit_event_writer_repository(client)

        with self.assertRaises(ClickHouseBatchWriteError) as exc_info:
            repository.write_batch_request_with_retry(
                ClickHouseBatchWriteRequest(rows=(_evaluate_row(),)),
                retry_policy=ClickHouseBatchWriteRetryPolicy(max_attempts=2, backoff_ms=0),
            )

        self.assertEqual(exc_info.exception.table_name, "defense_audit_events")
        self.assertEqual(exc_info.exception.attempted_row_count, 1)
        self.assertIn("replay", exc_info.exception.replay_hint.lower())

    def test_http_clickhouse_client_posts_jsoneachrow_insert_request(self) -> None:
        _RecordingClickHouseHandler.requests = []
        server = HTTPServer(("127.0.0.1", 0), _RecordingClickHouseHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HttpClickHouseBatchWriteClient(
                url=f"clickhouse://127.0.0.1:{server.server_port}/default",
                timeout_ms=1000,
            )
            repository = ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url=f"clickhouse://127.0.0.1:{server.server_port}/default",
                    table_name="defense_audit_events",
                    batch_size=1000,
                    timeout_ms=1000,
                ),
            )

            accepted_count = repository.write_batch([_evaluate_row()])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(accepted_count, 1)
        self.assertEqual(len(_RecordingClickHouseHandler.requests), 1)
        request = _RecordingClickHouseHandler.requests[0]
        self.assertEqual(request["query"]["database"], ["default"])
        self.assertIn("FORMAT JSONEachRow", request["query"]["query"][0])
        self.assertIn('"session_id":"sess-1"', str(request["body"]))
        self.assertIn('"raw_payload_json":"{\\"request_id\\":\\"req-1\\",\\"decision_id\\":\\"dec-1\\"}"', str(request["body"]))

    def test_env_surface_only_overrides_table_name(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            self.assertEqual(get_clickhouse_audit_table_from_env(), DEFAULT_CLICKHOUSE_AUDIT_TABLE)

        with patch.dict(os.environ, {"TM_CLICKHOUSE_AUDIT_TABLE": "audit_events_stage"}, clear=False):
            self.assertEqual(get_clickhouse_audit_table_from_env(), "audit_events_stage")


if __name__ == "__main__":
    unittest.main()
