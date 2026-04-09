from __future__ import annotations

import json
import unittest

from traffic_master_ai.defense.d0_mvp.state.etl_processed_ledger import (
    ETLProcessedS3ObjectIdentity,
    ETLProcessedS3ObjectLedger,
    build_etl_processed_s3_object_ledger_key,
)
from traffic_master_ai.defense.d0_mvp.state.keyspace import ETL_PROCESSED_KEY_PREFIX
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


class ETLProcessedLedgerTests(unittest.TestCase):
    def test_same_bucket_key_etag_builds_same_ledger_key(self) -> None:
        left = ETLProcessedS3ObjectIdentity(
            bucket="audit-bucket",
            object_key="ai-defense/audit/2026/04/09/part-0001.jsonl",
            etag='"etag-1"',
        )
        right = ETLProcessedS3ObjectIdentity(
            bucket="audit-bucket",
            object_key="ai-defense/audit/2026/04/09/part-0001.jsonl",
            etag='"etag-1"',
        )

        self.assertEqual(
            build_etl_processed_s3_object_ledger_key(left),
            build_etl_processed_s3_object_ledger_key(right),
        )

    def test_different_etag_builds_different_ledger_key(self) -> None:
        left = ETLProcessedS3ObjectIdentity(
            bucket="audit-bucket",
            object_key="ai-defense/audit/2026/04/09/part-0001.jsonl",
            etag='"etag-1"',
        )
        right = ETLProcessedS3ObjectIdentity(
            bucket="audit-bucket",
            object_key="ai-defense/audit/2026/04/09/part-0001.jsonl",
            etag='"etag-2"',
        )

        self.assertNotEqual(
            build_etl_processed_s3_object_ledger_key(left),
            build_etl_processed_s3_object_ledger_key(right),
        )

    def test_mark_completed_stores_json_value_and_ttl(self) -> None:
        redis = InMemoryRedis()
        ledger = ETLProcessedS3ObjectLedger(redis, ttl_s=300)
        identity = ETLProcessedS3ObjectIdentity(
            bucket="audit-bucket",
            object_key="ai-defense/audit/2026/04/09/part-0001.jsonl",
            etag='"etag-1"',
        )

        record = ledger.mark_completed(identity, row_count=1843, processed_at_ms=1775683200000)
        stored_key = ledger.key_for_object(identity)
        stored_value = redis.get(stored_key)

        self.assertIsNotNone(stored_value)
        self.assertTrue(stored_key.startswith(f"{ETL_PROCESSED_KEY_PREFIX}audit-bucket:"))
        self.assertEqual(record.row_count, 1843)
        self.assertGreater(redis.ttl(stored_key), 0)

        decoded = json.loads(str(stored_value))
        self.assertEqual(
            decoded,
            {
                "status": "completed",
                "bucket": "audit-bucket",
                "object_key": "ai-defense/audit/2026/04/09/part-0001.jsonl",
                "etag": '"etag-1"',
                "processed_at_ms": 1775683200000,
                "row_count": 1843,
            },
        )


if __name__ == "__main__":
    unittest.main()
