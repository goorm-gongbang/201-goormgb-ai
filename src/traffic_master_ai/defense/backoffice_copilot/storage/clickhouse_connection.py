"""Minimal ClickHouse connection surfaces for Backoffice Copilot storage tasks."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import cast
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ...storage_env import (
    DEFAULT_CLICKHOUSE_AUDIT_TABLE,
    DEFAULT_CLICKHOUSE_INGEST_BATCH_SIZE,
    DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS,
    load_clickhouse_storage_config_from_env,
)

DEFAULT_CLICKHOUSE_SESSION_ROLLUP_TABLE = "defense_session_rollups"
DEFAULT_CLICKHOUSE_MATCH_ROLLUP_TABLE = "defense_match_rollups"
DEFAULT_CLICKHOUSE_CANDIDATE_VIEW = "defense_post_review_candidates_v1"


class ClickHouseBatchWriteClient(Protocol):
    """Minimal client contract required by the raw-fact writer skeleton."""

    def execute(
        self,
        sql_text: str,
        rows: Sequence[Mapping[str, object]],
    ) -> Any:
        """Execute one batch insert operation."""


class ClickHouseSelectClient(Protocol):
    """Minimal client contract required by read-model reader skeletons."""

    def query(
        self,
        sql_text: str,
        params: Mapping[str, object],
    ) -> Sequence[Mapping[str, object]]:
        """Execute one read-model query and return mapping-like rows."""


@dataclass(slots=True, frozen=True)
class ClickHouseWriteConfig:
    """Minimal config surface for ClickHouse raw-fact writes.

    Network URL, auth, pool, and async insert settings are intentionally deferred.
    Task 14 exposes the minimum env-driven table, batch, timeout, and URL contract only.
    """

    url: str | None = None
    table_name: str = DEFAULT_CLICKHOUSE_AUDIT_TABLE
    batch_size: int = DEFAULT_CLICKHOUSE_INGEST_BATCH_SIZE
    timeout_ms: int = DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS


@dataclass(slots=True, frozen=True)
class ClickHouseReadModelConfig:
    """Minimal config surface for ClickHouse read-model access."""

    url: str | None = None
    session_rollup_table: str = DEFAULT_CLICKHOUSE_SESSION_ROLLUP_TABLE
    match_rollup_table: str = DEFAULT_CLICKHOUSE_MATCH_ROLLUP_TABLE
    candidate_view_name: str = DEFAULT_CLICKHOUSE_CANDIDATE_VIEW
    timeout_ms: int = DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS


@dataclass(slots=True, frozen=True)
class _ParsedClickHouseEndpoint:
    http_url: str
    database: str | None
    username: str | None
    password: str | None


class HttpClickHouseBatchWriteClient:
    """Minimal HTTP client for ClickHouse JSONEachRow batch inserts.

    This intentionally covers only the raw-fact ETL write surface. Richer driver
    features such as connection pooling, async insert settings, and native protocol
    support remain explicit future work.
    """

    def __init__(self, *, url: str, timeout_ms: int) -> None:
        self._endpoint = _parse_clickhouse_endpoint(url)
        self._timeout_seconds = max(timeout_ms, 1) / 1000.0

    def execute(
        self,
        sql_text: str,
        rows: Sequence[Mapping[str, object]],
    ) -> Any:
        query = _normalize_clickhouse_insert_query(sql_text)
        body = "\n".join(
            json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) for row in rows
        ).encode("utf-8")
        request = Request(
            url=_build_clickhouse_http_query_url(self._endpoint, query),
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-ndjson; charset=utf-8",
            },
        )
        if self._endpoint.username is not None:
            request.add_header(
                "Authorization",
                _build_basic_auth_header(
                    username=self._endpoint.username,
                    password=self._endpoint.password or "",
                ),
            )

        with urlopen(request, timeout=self._timeout_seconds) as response:
            response_body = response.read()
            if response.status >= 400:
                raise RuntimeError(
                    "ClickHouse HTTP insert failed "
                    f"(status={response.status}, body={response_body.decode('utf-8', errors='replace')})."
                )
            return response_body


class HttpClickHouseSelectClient:
    """Minimal HTTP client for ClickHouse read-model queries."""

    def __init__(self, *, url: str, timeout_ms: int) -> None:
        self._endpoint = _parse_clickhouse_endpoint(url)
        self._timeout_seconds = max(timeout_ms, 1) / 1000.0

    def query(
        self,
        sql_text: str,
        params: Mapping[str, object],
    ) -> Sequence[Mapping[str, object]]:
        rendered_query = _normalize_clickhouse_select_query(
            _render_clickhouse_query(sql_text, params)
        )
        request = Request(
            url=_build_clickhouse_http_query_url(self._endpoint, rendered_query),
            data=b"",
            method="POST",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        if self._endpoint.username is not None:
            request.add_header(
                "Authorization",
                _build_basic_auth_header(
                    username=self._endpoint.username,
                    password=self._endpoint.password or "",
                ),
            )

        with urlopen(request, timeout=self._timeout_seconds) as response:
            response_body = response.read()
            if response.status >= 400:
                raise RuntimeError(
                    "ClickHouse HTTP select failed "
                    f"(status={response.status}, body={response_body.decode('utf-8', errors='replace')})."
                )
            parsed = json.loads(response_body.decode("utf-8"))
        data = parsed.get("data")
        if not isinstance(data, list):
            raise RuntimeError("ClickHouse HTTP select response must include JSON data array.")
        return tuple(cast(Mapping[str, object], row) for row in data if isinstance(row, Mapping))


def get_clickhouse_url_from_env() -> str | None:
    """Return the configured ClickHouse URL or None when unset."""

    return load_clickhouse_storage_config_from_env().url


def get_clickhouse_audit_table_from_env() -> str:
    """Return the configured raw-fact table name using the shared task contract."""

    return load_clickhouse_storage_config_from_env().audit_table


def build_clickhouse_write_config_from_env() -> ClickHouseWriteConfig:
    """Build the minimal write config from env."""

    config = load_clickhouse_storage_config_from_env()
    return ClickHouseWriteConfig(
        url=config.url,
        table_name=config.audit_table,
        batch_size=config.ingest_batch_size,
        timeout_ms=config.ingest_timeout_ms,
    )


def build_clickhouse_batch_write_client(
    config: ClickHouseWriteConfig,
) -> ClickHouseBatchWriteClient:
    """Build the minimal HTTP batch-write client for raw-fact ETL."""

    if not config.url:
        raise ValueError("TM_CLICKHOUSE_URL must be set to build the ClickHouse writer client.")
    return HttpClickHouseBatchWriteClient(
        url=config.url,
        timeout_ms=config.timeout_ms,
    )


def build_clickhouse_select_client(
    config: ClickHouseReadModelConfig,
) -> ClickHouseSelectClient:
    """Build the minimal HTTP select client for read-model queries."""

    if not config.url:
        raise ValueError("TM_CLICKHOUSE_URL must be set to build the ClickHouse read-model client.")
    return HttpClickHouseSelectClient(
        url=config.url,
        timeout_ms=config.timeout_ms,
    )


def build_clickhouse_read_model_config_from_env() -> ClickHouseReadModelConfig:
    """Build the minimal read-model config from env."""

    config = load_clickhouse_storage_config_from_env()
    return ClickHouseReadModelConfig(
        url=config.url,
        timeout_ms=config.ingest_timeout_ms,
    )


def _parse_clickhouse_endpoint(url: str) -> _ParsedClickHouseEndpoint:
    parsed = urlsplit(url)
    scheme = parsed.scheme.strip().lower()
    if scheme not in {"clickhouse", "http", "https"}:
        raise ValueError(
            "TM_CLICKHOUSE_URL must use clickhouse://, http://, or https:// scheme."
        )
    if not parsed.hostname:
        raise ValueError("TM_CLICKHOUSE_URL must include a hostname.")

    http_scheme = "http" if scheme == "clickhouse" else scheme
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    database = path_segments[0] if path_segments else None
    query_items = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)]
    query_map = dict(query_items)
    if not database:
        database = query_map.get("database") or None

    host = parsed.hostname
    if host is None:
        raise ValueError("TM_CLICKHOUSE_URL must include a hostname.")
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"

    http_url = urlunsplit((http_scheme, netloc, "/", "", ""))
    return _ParsedClickHouseEndpoint(
        http_url=http_url,
        database=database,
        username=parsed.username,
        password=parsed.password,
    )


def _normalize_clickhouse_insert_query(sql_text: str) -> str:
    stripped = sql_text.strip()
    if stripped.endswith(" VALUES"):
        return stripped[:-7] + " FORMAT JSONEachRow"
    return stripped


def _build_clickhouse_http_query_url(endpoint: _ParsedClickHouseEndpoint, query: str) -> str:
    params: list[tuple[str, str]] = [("query", query)]
    if endpoint.database:
        params.append(("database", endpoint.database))
    return f"{endpoint.http_url}?{urlencode(params)}"


def _build_basic_auth_header(*, username: str, password: str) -> str:
    import base64

    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _normalize_clickhouse_select_query(sql_text: str) -> str:
    stripped = sql_text.strip()
    if stripped.endswith("FORMAT JSON"):
        return stripped
    return f"{stripped} FORMAT JSON"


def _render_clickhouse_query(sql_text: str, params: Mapping[str, object]) -> str:
    rendered = sql_text
    for key in sorted(params.keys(), key=len, reverse=True):
        rendered = rendered.replace(f":{key}", _serialize_clickhouse_query_value(params[key]))
    return rendered


def _serialize_clickhouse_query_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _quote_clickhouse_string(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "(" + ", ".join(_serialize_clickhouse_query_value(item) for item in value) + ")"
    raise TypeError(f"unsupported ClickHouse query parameter type: {type(value).__name__}")


def _quote_clickhouse_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
