from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from traffic_master_ai.defense.backoffice_copilot.storage import (
    ClickHouseMatchRollupQuery,
    ClickHousePostReviewCandidateQuery,
    ClickHouseReadModelConfig,
    ClickHouseMatchRollupReaderRepository,
    ClickHouseSessionRollupQuery,
    ClickHousePostReviewCandidateReaderRepository,
    ClickHouseSessionRollupReaderRepository,
    HttpClickHouseSelectClient,
    build_clickhouse_match_rollup_reader_repository,
    build_clickhouse_post_review_candidate_reader_repository,
    build_clickhouse_session_rollup_reader_repository,
    load_backoffice_clickhouse_read_model_input,
    parse_clickhouse_match_rollup_row,
    parse_clickhouse_post_review_candidate_row,
    parse_clickhouse_session_rollup_row,
    validate_clickhouse_match_rollup_query,
    validate_clickhouse_post_review_candidate_query,
    validate_clickhouse_session_rollup_query,
)
from traffic_master_ai.defense.backoffice_copilot.storage.validators import StorageValidationError


class _FakeSelectClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def query(self, sql_text: str, params: dict[str, object]) -> list[dict[str, object]]:
        self.calls.append((sql_text, params))
        if "defense_post_review_candidates_v1" in sql_text:
            return [
                {
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "session_id": "sess-2",
                    "first_ts_ms": 115,
                    "last_ts_ms": 190,
                    "latest_action": "THROTTLE",
                    "latest_risk_tier": "T2",
                    "latest_reason_code": "RULE_HIT",
                    "latest_policy_version": "policy-v1",
                    "block_action_count": 0,
                    "throttle_action_count": 1,
                    "challenge_issue_count": 1,
                    "challenge_verified_count": 0,
                    "candidate_reason": "throttle_action_detected",
                }
            ]
        if "defense_match_rollups" in sql_text:
            return [
                {
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "match_id": "687",
                    "session_count": 2,
                    "event_count": 5,
                    "block_action_count": 0,
                    "throttle_action_count": 1,
                    "challenge_issue_count": 1,
                    "challenge_verified_count": 1,
                    "latest_policy_version": "policy-v1",
                }
            ]
        return [
            {
                "window_start_ms": 100,
                "window_end_ms": 200,
                "session_id": "sess-1",
                "first_ts_ms": 110,
                "last_ts_ms": 180,
                "event_count": 3,
                "latest_flow_state": "F4M",
                "latest_action": "THROTTLE",
                "latest_risk_tier": "T2",
                "latest_reason_code": "RULE_HIT",
                "latest_policy_version": "policy-v1",
                "throttle_action_count": 1,
                "block_action_count": 0,
                "challenge_issue_count": 1,
                "challenge_verified_count": 1,
            }
        ]


class _RecordingSelectHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        self.__class__.requests.append(
            {
                "path": self.path,
                "query": parse_qs(urlsplit(self.path).query),
            }
        )
        body = json.dumps(
            {
                "data": [
                    {
                        "window_start_ms": 100,
                        "window_end_ms": 200,
                        "session_id": "sess-http",
                        "first_ts_ms": 110,
                        "last_ts_ms": 190,
                        "event_count": 2,
                        "latest_flow_state": "F4M",
                        "latest_action": "THROTTLE",
                        "latest_risk_tier": "T2",
                        "latest_reason_code": "RULE_HIT",
                        "latest_policy_version": "policy-v2",
                        "throttle_action_count": 1,
                        "block_action_count": 0,
                        "challenge_issue_count": 1,
                        "challenge_verified_count": 0,
                    }
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover
        return


class BackofficeCopilotClickHouseReadModelTests(unittest.TestCase):
    def test_read_queries_stay_window_centric(self) -> None:
        session_query = validate_clickhouse_session_rollup_query(
            ClickHouseSessionRollupQuery(window_start_ms=100, window_end_ms=200, limit=50)
        )
        match_query = validate_clickhouse_match_rollup_query(
            ClickHouseMatchRollupQuery(
                window_start_ms=100,
                window_end_ms=200,
                match_ids=("687",),
                limit=5,
            )
        )
        candidate_query = validate_clickhouse_post_review_candidate_query(
            ClickHousePostReviewCandidateQuery(
                window_start_ms=100,
                window_end_ms=200,
                session_ids=("sess-1",),
                limit=10,
            )
        )

        self.assertEqual(session_query.window_start_ms, 100)
        self.assertEqual(match_query.match_ids, ("687",))
        self.assertEqual(candidate_query.session_ids, ("sess-1",))

    def test_row_parsers_match_task_3_minimum_contract(self) -> None:
        rollup = parse_clickhouse_session_rollup_row(
            {
                "window_start_ms": 100,
                "window_end_ms": 200,
                "session_id": "sess-1",
                "first_ts_ms": 110,
                "last_ts_ms": 180,
                "event_count": 3,
                "latest_flow_state": "F4M",
                "latest_action": "THROTTLE",
                "latest_risk_tier": "T2",
                "latest_reason_code": "RULE_HIT",
                "latest_policy_version": "policy-v1",
                "throttle_action_count": 1,
                "block_action_count": 0,
                "challenge_issue_count": 1,
                "challenge_verified_count": 1,
            }
        )
        match_rollup = parse_clickhouse_match_rollup_row(
            {
                "window_start_ms": 100,
                "window_end_ms": 200,
                "match_id": "687",
                "session_count": 2,
                "event_count": 5,
                "block_action_count": 0,
                "throttle_action_count": 1,
                "challenge_issue_count": 1,
                "challenge_verified_count": 1,
                "latest_policy_version": "policy-v1",
            }
        )
        candidate = parse_clickhouse_post_review_candidate_row(
            {
                "window_start_ms": 100,
                "window_end_ms": 200,
                "session_id": "sess-2",
                "first_ts_ms": 115,
                "last_ts_ms": 190,
                "latest_action": "THROTTLE",
                "latest_risk_tier": "T2",
                "latest_reason_code": "RULE_HIT",
                "latest_policy_version": "policy-v1",
                "block_action_count": 0,
                "throttle_action_count": 1,
                "challenge_issue_count": 1,
                "challenge_verified_count": 0,
                "candidate_reason": "throttle_action_detected",
            }
        )

        self.assertEqual(rollup.event_count, 3)
        self.assertEqual(match_rollup.match_id, "687")
        self.assertEqual(rollup.latest_risk_tier, "T2")
        self.assertEqual(candidate.candidate_reason, "throttle_action_detected")
        self.assertFalse(hasattr(candidate, "match_id"))

    def test_row_parsers_reject_invalid_window_shapes(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_clickhouse_session_rollup_query(
                ClickHouseSessionRollupQuery(window_start_ms=200, window_end_ms=100)
            )

        with self.assertRaises(StorageValidationError):
            validate_clickhouse_match_rollup_query(
                ClickHouseMatchRollupQuery(window_start_ms=200, window_end_ms=100)
            )

        with self.assertRaises(StorageValidationError):
            parse_clickhouse_post_review_candidate_row(
                {
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "session_id": "sess-2",
                    "first_ts_ms": 220,
                    "last_ts_ms": 190,
                    "latest_action": "THROTTLE",
                    "latest_risk_tier": "T2",
                    "latest_reason_code": "RULE_HIT",
                    "latest_policy_version": "policy-v1",
                    "block_action_count": 0,
                    "throttle_action_count": 1,
                    "challenge_issue_count": 1,
                    "challenge_verified_count": 0,
                    "candidate_reason": "throttle_action_detected",
                }
            )

    def test_reader_repositories_keep_session_rollup_and_candidate_responsibility_separate(self) -> None:
        client = _FakeSelectClient()
        session_repository = build_clickhouse_session_rollup_reader_repository(client)
        match_repository = build_clickhouse_match_rollup_reader_repository(client)
        candidate_repository = build_clickhouse_post_review_candidate_reader_repository(client)

        session_rows = session_repository.read_rollups(
            ClickHouseSessionRollupQuery(window_start_ms=100, window_end_ms=200)
        )
        match_rows = match_repository.read_match_rollups(
            ClickHouseMatchRollupQuery(window_start_ms=100, window_end_ms=200)
        )
        candidate_rows = candidate_repository.read_candidates(
            ClickHousePostReviewCandidateQuery(window_start_ms=100, window_end_ms=200, limit=5)
        )

        self.assertEqual(len(session_rows), 1)
        self.assertEqual(len(match_rows), 1)
        self.assertEqual(len(candidate_rows), 1)
        self.assertIn("FROM defense_session_rollups", client.calls[0][0])
        self.assertIn("FROM defense_match_rollups", client.calls[1][0])
        self.assertIn("FROM defense_post_review_candidates_v1", client.calls[2][0])
        self.assertNotIn("defense_session_rollups", client.calls[2][0])

    def test_reader_sql_contract_keeps_window_filter_optional_session_filter_and_limit(self) -> None:
        session_repository = ClickHouseSessionRollupReaderRepository(
            client=_FakeSelectClient(),
            config=ClickHouseReadModelConfig(session_rollup_table="session_rollups_stage"),
        )
        match_repository = ClickHouseMatchRollupReaderRepository(
            client=_FakeSelectClient(),
            config=ClickHouseReadModelConfig(match_rollup_table="match_rollups_stage"),
        )
        candidate_repository = ClickHousePostReviewCandidateReaderRepository(
            client=_FakeSelectClient(),
            config=ClickHouseReadModelConfig(candidate_view_name="candidate_view_stage"),
        )

        session_sql = session_repository.select_sql_for(
            ClickHouseSessionRollupQuery(
                window_start_ms=100,
                window_end_ms=200,
                session_ids=("sess-1", "sess-2"),
                limit=10,
            )
        )
        match_sql = match_repository.select_sql_for(
            ClickHouseMatchRollupQuery(
                window_start_ms=100,
                window_end_ms=200,
                match_ids=("687",),
                limit=2,
            )
        )
        candidate_sql = candidate_repository.select_sql_for(
            ClickHousePostReviewCandidateQuery(
                window_start_ms=100,
                window_end_ms=200,
                session_ids=("sess-3",),
                limit=5,
            )
        )

        self.assertIn("FROM session_rollups_stage", session_sql)
        self.assertIn("session_id IN :session_ids", session_sql)
        self.assertIn("LIMIT :limit", session_sql)
        self.assertIn("FROM match_rollups_stage", match_sql)
        self.assertIn("match_id IN :match_ids", match_sql)
        self.assertIn("LIMIT :limit", match_sql)
        self.assertIn("FROM candidate_view_stage", candidate_sql)
        self.assertIn("session_id IN :session_ids", candidate_sql)
        self.assertIn("LIMIT :limit", candidate_sql)

    def test_backoffice_input_bundle_uses_read_models_only(self) -> None:
        client = _FakeSelectClient()
        session_repository = build_clickhouse_session_rollup_reader_repository(client)
        candidate_repository = build_clickhouse_post_review_candidate_reader_repository(client)

        bundle = load_backoffice_clickhouse_read_model_input(
            window_start_ms=100,
            window_end_ms=200,
            session_rollup_repository=session_repository,
            candidate_repository=candidate_repository,
            limit=3,
        )

        self.assertEqual(tuple(row.session_id for row in bundle.session_rollups), ("sess-1",))
        self.assertEqual(tuple(row.session_id for row in bundle.candidate_rows), ("sess-2",))
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all("defense_audit_events" not in sql_text for sql_text, _ in client.calls))

    def test_http_select_client_renders_clickhouse_query_with_real_object_name(self) -> None:
        _RecordingSelectHandler.requests = []
        server = HTTPServer(("127.0.0.1", 0), _RecordingSelectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HttpClickHouseSelectClient(
                url=f"clickhouse://127.0.0.1:{server.server_port}/default",
                timeout_ms=1000,
            )
            repository = ClickHouseSessionRollupReaderRepository(
                client=client,
                config=ClickHouseReadModelConfig(
                    url=f"clickhouse://127.0.0.1:{server.server_port}/default",
                    session_rollup_table="defense_session_rollups",
                    timeout_ms=1000,
                ),
            )

            rows = repository.read_rollups(
                ClickHouseSessionRollupQuery(
                    window_start_ms=100,
                    window_end_ms=200,
                    session_ids=("sess-http",),
                    limit=1,
                )
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].session_id, "sess-http")
        rendered_query = _RecordingSelectHandler.requests[0]["query"]["query"][0]
        self.assertIn("FROM defense_session_rollups", rendered_query)
        self.assertIn("session_id IN ('sess-http')", rendered_query)
        self.assertIn("FORMAT JSON", rendered_query)


if __name__ == "__main__":
    unittest.main()
