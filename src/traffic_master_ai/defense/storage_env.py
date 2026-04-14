"""Minimal storage/runtime env configuration loaders for DB-build tasks."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DEFENSE_AUDIT_LOG_PATH = "/tmp/logs/defense_decision_audit.jsonl"
DEFAULT_WAREHOUSE_FILENAME = "/tmp/logs/defense_audit_events.jsonl"
DEFAULT_POLICY_STORE_PATH = "/tmp/logs/policy_store.json"
DEFAULT_POLICY_CACHE_SECONDS = 5
DEFAULT_POLICY_PROJECTION_MAX_STALENESS_MS = 300000
DEFAULT_S3_PREFIX = "ai-defense/audit/"
DEFAULT_S3_ARCHIVE_INTERVAL_SECONDS = 300
RECOMMENDED_STAGING_S3_ARCHIVE_INTERVAL_SECONDS = 60
RECOMMENDED_PROD_S3_ARCHIVE_INTERVAL_SECONDS = 300
DEFAULT_CLICKHOUSE_AUDIT_TABLE = "defense_audit_events"
DEFAULT_CLICKHOUSE_INGEST_BATCH_SIZE = 256
DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS = 5000
RECOMMENDED_STAGING_CLICKHOUSE_INGEST_BATCH_SIZE = 128
RECOMMENDED_PROD_CLICKHOUSE_INGEST_BATCH_SIZE = 256
DEFAULT_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS = 3
DEFAULT_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS = 200
RECOMMENDED_STAGING_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS = 3
RECOMMENDED_PROD_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS = 3
RECOMMENDED_STAGING_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS = 200
RECOMMENDED_PROD_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS = 200
DEFAULT_ETL_PROCESSED_LEDGER_TTL_SECONDS = 2592000
RECOMMENDED_ETL_PROCESSED_LEDGER_TTL_SECONDS = 2592000
DEFAULT_PROJECTION_RETRY_MAX_ATTEMPTS = 2
DEFAULT_PROJECTION_RETRY_BACKOFF_MS = 50
DEFAULT_POLICY_OPTIMIZER_WINDOW_SECONDS = 600
DEFAULT_POLICY_OPTIMIZER_CANARY_RATIO = 0.05
DEFAULT_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS = 300
DEFAULT_POLICY_OPTIMIZER_ROLLOUT_ID = "offline-optimizer-default"
DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS = 300


class StorageOperationalConfigError(ValueError):
    """Raised when prod-required storage/runtime env is missing or unsafe."""


@dataclass(slots=True, frozen=True)
class AuditLogConfig:
    """Config surface for append-only audit JSONL path."""

    file_path: str = DEFAULT_DEFENSE_AUDIT_LOG_PATH


@dataclass(slots=True, frozen=True)
class WarehouseFileConfig:
    """Config surface for the local JSONL warehouse MVP path."""

    file_path: str = DEFAULT_WAREHOUSE_FILENAME


@dataclass(slots=True, frozen=True)
class RuntimePolicyConfig:
    """Config surface for runtime policy loader / file fallback."""

    store_path: str = DEFAULT_POLICY_STORE_PATH
    cache_seconds: int = DEFAULT_POLICY_CACHE_SECONDS
    rollout_salt: str = ""
    allow_local_fallback: bool = False
    projection_max_staleness_ms: int | None = DEFAULT_POLICY_PROJECTION_MAX_STALENESS_MS

    @property
    def has_explicit_rollout_salt(self) -> bool:
        return bool(self.rollout_salt)

    @property
    def strict_authority(self) -> bool:
        return not self.allow_local_fallback


@dataclass(slots=True, frozen=True)
class RuntimeRedisConfig:
    """Config surface for runtime/projection Redis backend selection."""

    redis_url: str | None
    allow_memory_fallback: bool


@dataclass(slots=True, frozen=True)
class S3ArchiveConfig:
    """Config surface for S3 archive / ETL source."""

    bucket: str | None
    region: str | None = None
    prefix: str = DEFAULT_S3_PREFIX
    archive_interval_seconds: int = DEFAULT_S3_ARCHIVE_INTERVAL_SECONDS

    @property
    def archive_enabled(self) -> bool:
        return bool(self.bucket)


@dataclass(slots=True, frozen=True)
class PostgresStorageConfig:
    """Config surface for PostgreSQL-backed workers and repositories."""

    url: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.url)


@dataclass(slots=True, frozen=True)
class ClickHouseStorageConfig:
    """Config surface for ClickHouse writer/read/ingest skeletons."""

    url: str | None
    audit_table: str = DEFAULT_CLICKHOUSE_AUDIT_TABLE
    ingest_batch_size: int = DEFAULT_CLICKHOUSE_INGEST_BATCH_SIZE
    ingest_timeout_ms: int = DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS
    write_retry_max_attempts: int = DEFAULT_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS
    write_retry_backoff_ms: int = DEFAULT_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS

    @property
    def enabled(self) -> bool:
        return bool(self.url)


@dataclass(slots=True, frozen=True)
class ETLProcessedLedgerConfig:
    ttl_seconds: int = DEFAULT_ETL_PROCESSED_LEDGER_TTL_SECONDS


@dataclass(slots=True, frozen=True)
class ProjectionSyncConfig:
    """Config surface for PostgreSQL -> Redis sync/resync retries."""

    retry_max_attempts: int = DEFAULT_PROJECTION_RETRY_MAX_ATTEMPTS
    retry_backoff_ms: int = DEFAULT_PROJECTION_RETRY_BACKOFF_MS


@dataclass(slots=True, frozen=True)
class PolicyOptimizerConfig:
    enabled: bool = False
    dry_run: bool = False
    apply_enabled: bool = False
    bootstrap_baseline: bool = False
    window_seconds: int = DEFAULT_POLICY_OPTIMIZER_WINDOW_SECONDS
    canary_ratio: float = DEFAULT_POLICY_OPTIMIZER_CANARY_RATIO
    min_apply_cooldown_seconds: int = DEFAULT_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS
    rollout_id: str = DEFAULT_POLICY_OPTIMIZER_ROLLOUT_ID
    lock_ttl_seconds: int = DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS


@dataclass(slots=True, frozen=True)
class ETLWorkerConfig:
    """Combined config surface for the current ETL worker prototype."""

    s3: S3ArchiveConfig
    postgres: PostgresStorageConfig
    clickhouse: ClickHouseStorageConfig
    processed_ledger: ETLProcessedLedgerConfig = field(
        default_factory=ETLProcessedLedgerConfig
    )

    @property
    def can_run_current_postgres_prototype(self) -> bool:
        return self.s3.archive_enabled and self.postgres.enabled


def load_runtime_environment_name_from_env() -> str:
    """Load the coarse deployment mode used for prod-only guardrails."""

    return _clean_text(os.getenv("TM_ENV"), default="dev").lower()


def is_production_environment() -> bool:
    """Return True when prod-only guardrails must be enforced."""

    return load_runtime_environment_name_from_env() in {"prod", "production"}


def load_audit_log_config_from_env() -> AuditLogConfig:
    """Load the append-only audit log path contract from env."""

    return AuditLogConfig(
        file_path=_clean_text(
            os.getenv("TM_DEFENSE_AUDIT_LOG_PATH"),
            default=DEFAULT_DEFENSE_AUDIT_LOG_PATH,
        )
    )


def load_warehouse_file_config_from_env() -> WarehouseFileConfig:
    """Load the local JSONL warehouse path.

    Note: `TM_WAREHOUSE_FILENAME` is current-code-only and not part of Task 6 cross-store env matrix.
    It remains for JSONL MVP compatibility until ClickHouse wiring replaces the local warehouse path.
    """

    return WarehouseFileConfig(
        file_path=_clean_text(
            os.getenv("TM_WAREHOUSE_FILENAME"),
            default=DEFAULT_WAREHOUSE_FILENAME,
        )
    )


def load_runtime_policy_config_from_env() -> RuntimePolicyConfig:
    """Load runtime policy loader settings from env."""

    is_ci = os.getenv("CI", "false").strip().lower() == "true"
    return RuntimePolicyConfig(
        store_path=_clean_text(
            os.getenv("TM_POLICY_STORE_PATH"),
            default=DEFAULT_POLICY_STORE_PATH,
        ),
        cache_seconds=_clean_int(
            os.getenv("TM_POLICY_CACHE_SECONDS"),
            default=DEFAULT_POLICY_CACHE_SECONDS,
            env_name="TM_POLICY_CACHE_SECONDS",
        ),
        rollout_salt=_clean_text(os.getenv("TM_ROLLOUT_SALT"), default=""),
        allow_local_fallback=_clean_bool(
            os.getenv("TM_POLICY_ALLOW_LOCAL_FALLBACK"),
            default=is_ci,
        ),
        projection_max_staleness_ms=_clean_optional_int(
            os.getenv("TM_POLICY_PROJECTION_MAX_STALENESS_MS"),
            default=DEFAULT_POLICY_PROJECTION_MAX_STALENESS_MS,
            env_name="TM_POLICY_PROJECTION_MAX_STALENESS_MS",
        ),
    )


def load_runtime_redis_config_from_env() -> RuntimeRedisConfig:
    """Load runtime/projection Redis backend settings from env."""

    redis_url = _clean_optional_text(os.getenv("TM_REDIS_URL"))
    is_ci = os.getenv("CI", "false").strip().lower() == "true"
    allow_memory_fallback = _clean_bool(
        os.getenv("TM_ALLOW_IN_MEMORY_REDIS"),
        default=is_ci,
    )
    return RuntimeRedisConfig(
        redis_url=redis_url,
        allow_memory_fallback=allow_memory_fallback,
    )


def load_s3_archive_config_from_env() -> S3ArchiveConfig:
    """Load S3 archive / ETL source settings from env."""

    return S3ArchiveConfig(
        bucket=_clean_optional_text(os.getenv("TM_S3_BUCKET")),
        region=_clean_optional_text(os.getenv("TM_S3_REGION")),
        prefix=_clean_text(os.getenv("TM_S3_PREFIX"), default=DEFAULT_S3_PREFIX),
        archive_interval_seconds=_clean_positive_int(
            os.getenv("TM_S3_ARCHIVE_INTERVAL_SECONDS"),
            default=DEFAULT_S3_ARCHIVE_INTERVAL_SECONDS,
            env_name="TM_S3_ARCHIVE_INTERVAL_SECONDS",
        ),
    )


def load_postgres_storage_config_from_env(*, required: bool = False) -> PostgresStorageConfig:
    """Load PostgreSQL connection config from env."""

    url = _clean_optional_text(os.getenv("TM_PG_URL"))
    if required and not url:
        raise ValueError("TM_PG_URL must be set to use PostgreSQL-backed storage.")
    return PostgresStorageConfig(url=url)


def load_clickhouse_storage_config_from_env() -> ClickHouseStorageConfig:
    """Load ClickHouse storage settings from env."""

    return ClickHouseStorageConfig(
        url=_clean_optional_text(os.getenv("TM_CLICKHOUSE_URL")),
        audit_table=_clean_text(
            os.getenv("TM_CLICKHOUSE_AUDIT_TABLE"),
            default=DEFAULT_CLICKHOUSE_AUDIT_TABLE,
        ),
        ingest_batch_size=_clean_positive_int(
            os.getenv("TM_CLICKHOUSE_INGEST_BATCH_SIZE"),
            default=DEFAULT_CLICKHOUSE_INGEST_BATCH_SIZE,
            env_name="TM_CLICKHOUSE_INGEST_BATCH_SIZE",
        ),
        ingest_timeout_ms=_clean_positive_int(
            os.getenv("TM_CLICKHOUSE_INGEST_TIMEOUT_MS"),
            default=DEFAULT_CLICKHOUSE_INGEST_TIMEOUT_MS,
            env_name="TM_CLICKHOUSE_INGEST_TIMEOUT_MS",
        ),
        write_retry_max_attempts=_clean_positive_int(
            os.getenv("TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS"),
            default=DEFAULT_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS,
            env_name="TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS",
        ),
        write_retry_backoff_ms=_clean_int(
            os.getenv("TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS"),
            default=DEFAULT_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS,
            env_name="TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS",
        ),
    )


def load_etl_processed_ledger_config_from_env() -> ETLProcessedLedgerConfig:
    return ETLProcessedLedgerConfig(
        ttl_seconds=_clean_positive_int(
            os.getenv("TM_ETL_PROCESSED_LEDGER_TTL_SECONDS"),
            default=DEFAULT_ETL_PROCESSED_LEDGER_TTL_SECONDS,
            env_name="TM_ETL_PROCESSED_LEDGER_TTL_SECONDS",
        )
    )


def load_projection_sync_config_from_env() -> ProjectionSyncConfig:
    """Load retry settings for PostgreSQL -> Redis sync/resync."""

    return ProjectionSyncConfig(
        retry_max_attempts=_clean_int(
            os.getenv("TM_PROJECTION_RETRY_MAX_ATTEMPTS"),
            default=DEFAULT_PROJECTION_RETRY_MAX_ATTEMPTS,
            env_name="TM_PROJECTION_RETRY_MAX_ATTEMPTS",
        ),
        retry_backoff_ms=_clean_int(
            os.getenv("TM_PROJECTION_RETRY_BACKOFF_MS"),
            default=DEFAULT_PROJECTION_RETRY_BACKOFF_MS,
            env_name="TM_PROJECTION_RETRY_BACKOFF_MS",
        ),
    )


def load_policy_optimizer_config_from_env() -> PolicyOptimizerConfig:
    return PolicyOptimizerConfig(
        enabled=_clean_bool(os.getenv("TM_POLICY_OPTIMIZER_ENABLED"), default=False),
        dry_run=_clean_bool(os.getenv("TM_POLICY_OPTIMIZER_DRY_RUN"), default=False),
        apply_enabled=_clean_bool(
            os.getenv("TM_POLICY_OPTIMIZER_APPLY_ENABLED"),
            default=False,
        ),
        bootstrap_baseline=_clean_bool(
            os.getenv("TM_POLICY_OPTIMIZER_BOOTSTRAP_BASELINE"),
            default=False,
        ),
        window_seconds=_clean_positive_int(
            os.getenv("TM_POLICY_OPTIMIZER_WINDOW_SECONDS"),
            default=DEFAULT_POLICY_OPTIMIZER_WINDOW_SECONDS,
            env_name="TM_POLICY_OPTIMIZER_WINDOW_SECONDS",
        ),
        canary_ratio=_clean_ratio(
            os.getenv("TM_POLICY_OPTIMIZER_CANARY_RATIO"),
            default=DEFAULT_POLICY_OPTIMIZER_CANARY_RATIO,
            env_name="TM_POLICY_OPTIMIZER_CANARY_RATIO",
        ),
        min_apply_cooldown_seconds=_clean_positive_int(
            os.getenv("TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS"),
            default=DEFAULT_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS,
            env_name="TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS",
        ),
        rollout_id=_clean_text(
            os.getenv("TM_POLICY_OPTIMIZER_ROLLOUT_ID"),
            default=DEFAULT_POLICY_OPTIMIZER_ROLLOUT_ID,
        ),
        lock_ttl_seconds=_clean_positive_int(
            os.getenv("TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS"),
            default=DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS,
            env_name="TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS",
        ),
    )


def load_etl_worker_config_from_env() -> ETLWorkerConfig:
    """Load the current ETL worker's storage config bundle from env."""

    return ETLWorkerConfig(
        s3=load_s3_archive_config_from_env(),
        postgres=load_postgres_storage_config_from_env(required=False),
        clickhouse=load_clickhouse_storage_config_from_env(),
        processed_ledger=load_etl_processed_ledger_config_from_env(),
    )


def validate_runtime_policy_env_for_prod() -> None:
    """Fail fast when prod runtime policy authority env is missing or unsafe."""

    if not is_production_environment():
        return

    redis_config = load_runtime_redis_config_from_env()
    policy_config = load_runtime_policy_config_from_env()
    if not redis_config.redis_url:
        raise StorageOperationalConfigError(
            "TM_REDIS_URL must be set when TM_ENV=prod for strict runtime authority."
        )
    if not policy_config.rollout_salt:
        raise StorageOperationalConfigError(
            "TM_ROLLOUT_SALT must be set when TM_ENV=prod for deterministic policy rollout."
        )
    if policy_config.allow_local_fallback:
        raise StorageOperationalConfigError(
            "TM_POLICY_ALLOW_LOCAL_FALLBACK must be false when TM_ENV=prod."
        )
    if redis_config.allow_memory_fallback:
        raise StorageOperationalConfigError(
            "TM_ALLOW_IN_MEMORY_REDIS must be false when TM_ENV=prod."
        )


def validate_control_plane_projection_env_for_prod() -> None:
    """Fail fast when prod projection sync env is missing or unsafe."""

    if not is_production_environment():
        return

    postgres_config = load_postgres_storage_config_from_env(required=False)
    redis_config = load_runtime_redis_config_from_env()
    if not postgres_config.enabled:
        raise StorageOperationalConfigError(
            "TM_PG_URL must be set when TM_ENV=prod for PostgreSQL authoritative control-plane."
        )
    if not redis_config.redis_url:
        raise StorageOperationalConfigError(
            "TM_REDIS_URL must be set when TM_ENV=prod for Redis projection sync."
        )


def validate_clickhouse_ingest_env_for_prod() -> None:
    """Fail fast when prod ClickHouse ingest env is missing or unsafe."""

    if not is_production_environment():
        return

    etl_config = load_etl_worker_config_from_env()
    redis_config = load_runtime_redis_config_from_env()
    if not etl_config.s3.archive_enabled:
        raise StorageOperationalConfigError(
            "TM_S3_BUCKET must be set when TM_ENV=prod for archive-backed ClickHouse ingest."
        )
    if not etl_config.clickhouse.enabled:
        raise StorageOperationalConfigError(
            "TM_CLICKHOUSE_URL must be set when TM_ENV=prod for ClickHouse ingest."
        )
    if not redis_config.redis_url:
        raise StorageOperationalConfigError(
            "TM_REDIS_URL must be set when TM_ENV=prod for ClickHouse ingest processed-key ledger."
        )


def _clean_optional_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned


def _clean_text(raw: str | None, *, default: str) -> str:
    cleaned = _clean_optional_text(raw)
    return cleaned if cleaned is not None else default


def _clean_int(raw: str | None, *, default: int, env_name: str) -> int:
    cleaned = _clean_optional_text(raw)
    if cleaned is None:
        return default
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer.") from exc


def _clean_positive_int(raw: str | None, *, default: int, env_name: str) -> int:
    value = _clean_int(raw, default=default, env_name=env_name)
    if value <= 0:
        raise ValueError(f"{env_name} must be a positive integer.")
    return value


def _clean_ratio(raw: str | None, *, default: float, env_name: str) -> float:
    cleaned = _clean_optional_text(raw)
    if cleaned is None:
        return default
    try:
        value = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be greater than 0 and less than or equal to 1.") from exc
    if value <= 0.0 or value > 1.0:
        raise ValueError(f"{env_name} must be greater than 0 and less than or equal to 1.")
    return value


def _clean_optional_int(raw: str | None, *, default: int | None, env_name: str) -> int | None:
    cleaned = _clean_optional_text(raw)
    if cleaned is None:
        return default
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer.") from exc


def _clean_bool(raw: str | None, *, default: bool) -> bool:
    cleaned = _clean_optional_text(raw)
    if cleaned is None:
        return default
    lowered = cleaned.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        "Boolean env values must be one of: true/false, 1/0, yes/no, on/off."
    )
