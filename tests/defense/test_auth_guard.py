from __future__ import annotations

import httpx
import pytest

from traffic_master_ai.defense.auth_guard import AuthGuardBlockService, AuthGuardConfig


class _FakeHttpClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        self.calls.append({
            "url": url,
            "headers": headers,
            "timeout": timeout,
        })
        return self.response

    def close(self) -> None:
        return None


def test_auth_guard_block_service_posts_expected_request(
) -> None:
    fake_client = _FakeHttpClient(
        httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "유저 차단 성공",
                "data": {"userId": 42, "status": "BLOCKED"},
            },
        )
    )
    service = AuthGuardBlockService(
        AuthGuardConfig(
            base_url="http://auth-guard:8080/auth",
            internal_api_key="test-key",
            timeout_seconds=1.25,
        ),
        http_client=fake_client,
    )

    result = service.block_user(
        user_id="42",
        session_id="sess-1",
        trace_id="trace-1",
        trigger="unit_test",
    )

    assert result.outcome == "blocked"
    assert fake_client.calls == [{
        "url": "http://auth-guard:8080/auth/internal/users/42/block",
        "headers": {"X-Internal-Api-Key": "test-key"},
        "timeout": 1.25,
    }]


@pytest.mark.parametrize(
    ("status_code", "expected_outcome"),
    [
        (403, "forbidden"),
        (409, "already_blocked"),
        (404, "not_found"),
        (401, "unauthorized"),
    ],
)
def test_auth_guard_block_service_categorizes_non_200_responses(
    status_code: int,
    expected_outcome: str,
) -> None:
    fake_client = _FakeHttpClient(
        httpx.Response(
            status_code,
            json={
                "code": "ANY",
                "message": "response",
            },
        )
    )
    service = AuthGuardBlockService(
        AuthGuardConfig(
            base_url="http://auth-guard:8080/auth",
            internal_api_key="test-key",
        ),
        http_client=fake_client,
    )

    result = service.block_user(
        user_id="42",
        session_id="sess-1",
        trace_id="trace-1",
        trigger="unit_test",
    )

    assert result.outcome == expected_outcome
    assert result.http_status == status_code
