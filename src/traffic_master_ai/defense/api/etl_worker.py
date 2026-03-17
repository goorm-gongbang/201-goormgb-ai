from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Mapping

import boto3
from sqlalchemy import Column, DateTime, String, Table, MetaData
from sqlalchemy.dialects.postgresql import JSONB

from .database import engine

logger = logging.getLogger(__name__)

metadata = MetaData()

# Define the audit events table using metadata for flexibility
audit_events = Table(
    "defense_audit_events",
    metadata,
    Column("id", String, primary_key=True),  # decision_id or composite
    Column("ts_ms", DateTime, index=True),
    Column("session_id", String, index=True),
    Column("event_type", String, index=True),
    Column("payload", JSONB),
    Column("created_at", DateTime, default=datetime.now(UTC)),
)


class ETLWorker:
    """ETL process to move logs from S3 to PostgreSQL."""

    def __init__(self, s3_bucket: str) -> None:
        self.s3_bucket = s3_bucket
        self.s3 = boto3.client("s3")
        self.engine = engine

    def run_once(self) -> int:
        """Scan S3 for new logs and insert into DB."""
        if not self.engine:
            logger.warning("PostgreSQL engine not configured. Skipping ETL.")
            return 0

        # Note: In a real prod environment, we would use S3 Event Notifications (SQS/Lambda).
        # For this PoC/Phase 2, we list the bucket's recent prefix.
        count = 0
        try:
            # Simple list operation for PoC
            response = self.s3.list_objects_v2(Bucket=self.s3_bucket, Prefix="ai-defense/audit/")
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".jsonl"):
                    continue
                
                count += self._process_s3_file(key)
        except Exception as exc:
            logger.error("ETL process failed: %s", exc)
        
        return count

    def _process_s3_file(self, key: str) -> int:
        """Download file from S3 and upsert rows."""
        count = 0
        try:
            response = self.s3.get_object(Bucket=self.s3_bucket, Key=key)
            lines = response["Body"].read().decode("utf-8").splitlines()
            
            with self.engine.begin() as conn:
                for line in lines:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    
                    # Normalize and Insert
                    stmt = audit_events.insert().values(
                        id=payload.get("decision_id") or payload.get("challenge_id") or os.urandom(8).hex(),
                        ts_ms=datetime.fromtimestamp(payload.get("ts_ms", 0) / 1000.0, UTC),
                        session_id=payload.get("session_id"),
                        event_type=payload.get("event_type"),
                        payload=payload
                    )
                    # Simple insert for MVP; duplicate handling would be added for Staging
                    conn.execute(stmt)
                    count += 1
            
            # Optional: Move key to /processed/ folder
            return count
        except Exception as exc:
            logger.error("Failed to process S3 key %s: %s", key, exc)
            return 0


def run_etl():
    """CLI entry point for the ETL worker."""
    bucket = os.getenv("TM_S3_BUCKET")
    if not bucket:
        print("TM_S3_BUCKET must be set to run ETL worker.")
        return
    
    worker = ETLWorker(s3_bucket=bucket)
    total = worker.run_once()
    print(f"ETL completed. Processed {total} rows.")


if __name__ == "__main__":
    run_etl()
