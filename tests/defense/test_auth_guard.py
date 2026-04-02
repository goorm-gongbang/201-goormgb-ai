from __future__ import annotations

import httpx
import pytest

from traffic_master_ai.defense.auth_guard import AuthGuardBlockService, AuthGuardConfig


def test_auth_guard_block_service_posts_expected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "유저 차단 성공",
                "data": {"userId": 42, "status": "BLOCKED"},
            },
        )

    monkeypatch.setattr("traffic_master_ai.defense.auth_guard.httpx.post", _fake_post)
    service = AuthGuardBlockService(
        AuthGuardConfig(
            base_url="http://auth-guard:8080/auth",
            internal_api_key="test-key",
            timeout_seconds=1.25,
        )
    )

    result = service.block_user(
        user_id="42",
        session_id="sess-1",
        trace_id="trace-1",
        trigger="unit_test",
    )

    assert result.outcome == "blocked"
    assert captured["url"] == "http://auth-guard:8080/auth/internal/users/42/block"
    assert captured["headers"] == {"X-Internal-Api-Key": "test-key"}
    assert captured["timeout"] == 1.25


@pytest.mark.parametrize(
    ("status_code", "expected_outcome"),
    [
        (409, "already_blocked"),
        (404, "not_found"),
        (401, "unauthorized"),
    ],
)
def test_auth_guard_block_service_categorizes_non_200_responses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_outcome: str,
) -> None:
    def _fake_post(url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        del url, headers, timeout
        return httpx.Response(
            status_code,
            json={
                "code": "ANY",
                "message": "response",
            },
        )

    monkeypatch.setattr("traffic_master_ai.defense.auth_guard.httpx.post", _fake_post)
    service = AuthGuardBlockService(
        AuthGuardConfig(
            base_url="http://auth-guard:8080/auth",
            internal_api_key="test-key",
        )
    )

    result = service.block_user(
        user_id="42",
        session_id="sess-1",
        trace_id="trace-1",
        trigger="unit_test",
    )

    assert result.outcome == expected_outcome
    assert result.http_status == status_code
