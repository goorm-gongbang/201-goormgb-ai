import tempfile
import unittest
from pathlib import Path

from traffic_master_ai.defense.d0_mvp.optimizer.audit_summarizer import AuditSummarizer
from traffic_master_ai.defense.d0_mvp.optimizer.effect_evaluator import LLMCallResult


class _CapturingLLMCaller:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call(
        self,
        *,
        system_prompt: str,
        user_input: str,
        max_output_tokens: int,
        timeout_ms: int,
        trace_name: str | None = None,
        trace_metadata: dict[str, object] | None = None,
    ) -> LLMCallResult:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_input": user_input,
                "max_output_tokens": max_output_tokens,
                "timeout_ms": timeout_ms,
                "trace_name": trace_name,
                "trace_metadata": trace_metadata,
            }
        )
        return LLMCallResult(
            success=True,
            output_text="LLM summary",
            latency_ms=321,
            tokens_in=21,
            tokens_out=9,
        )


class TestAuditSummarizerLangSmith(unittest.TestCase):
    def test_summarize_passes_trace_name_and_metadata_to_llm_caller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            caller = _CapturingLLMCaller()
            summarizer = AuditSummarizer(
                file_path=str(Path(tmp_dir) / "summary.jsonl"),
                min_events_total=1,
                cooldown_seconds=0,
                llm_caller=caller,
            )

            result = summarizer.summarize(
                metrics_snapshot={
                    "events_total": 12,
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "policy_version": "policy-v1",
                    "tier_distribution": {"T0": 8, "T1": 4},
                    "action_distribution": {"NONE": 10, "THROTTLE": 2},
                    "s3_pass_rate": 0.95,
                    "s3_temp_lock_rate": 0.01,
                    "block_rate": 0.002,
                    "avg_throttle_delay_ms": 90,
                },
                sampled_traces=[{"traceId": "trace-1"}],
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.summary_text, "LLM summary")
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(caller.calls[0]["trace_name"], "policy_optimizer.audit_summary")
        self.assertEqual(
            caller.calls[0]["trace_metadata"],
            {
                "feature_name": "policy_optimizer",
                "agent_step_name": "audit_summary",
                "environment": "dev",
                "window_start_ms": 100,
                "window_end_ms": 200,
                "policy_version": "policy-v1",
                "owner_team": "TM_AI",
            },
        )


if __name__ == "__main__":
    unittest.main()
