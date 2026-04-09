import json
import unittest
from unittest.mock import MagicMock, patch

from traffic_master_ai.defense.d0_mvp.optimizer.effect_evaluator import (
    OpenAICompatibleLLMCaller,
)


class TestEffectEvaluatorOpenAiCaller(unittest.TestCase):
    class _FakeTrace:
        def __init__(self) -> None:
            self.recorded_usage: dict | None = None
            self.recorded_output: dict | None = None
            self.recorded_errors: list[str] = []

        def __enter__(self) -> "TestEffectEvaluatorOpenAiCaller._FakeTrace":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def record_usage_metadata(self, usage_metadata: dict | None) -> None:
            self.recorded_usage = usage_metadata

        def record_output(self, output_payload: dict | None) -> None:
            self.recorded_output = output_payload

        def record_error(self, exc: Exception | str) -> None:
            self.recorded_errors.append(str(exc))

        def get_langsmith_link(self) -> dict[str, str]:
            return {}

    def _mock_urlopen_response(self, content_text: str, usage: dict | None = None) -> MagicMock:
        mock_response = MagicMock()
        payload = {
            "choices": [{"message": {"content": content_text}}],
        }
        if usage is not None:
            payload["usage"] = usage
        mock_response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_response
        return mock_context_manager

    @patch("traffic_master_ai.defense.d0_mvp.optimizer.effect_evaluator.start_langsmith_llm_trace")
    @patch("urllib.request.urlopen")
    def test_openai_caller_records_langsmith_usage_and_metadata(
        self,
        mock_urlopen: MagicMock,
        mock_start_trace: MagicMock,
    ) -> None:
        mock_urlopen.return_value = self._mock_urlopen_response(
            "{\"status\":\"LIVE_OK\"}",
            usage={"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
        )
        fake_trace = self._FakeTrace()
        mock_start_trace.return_value = fake_trace
        caller = OpenAICompatibleLLMCaller(
            api_key="test-api-key",
            model="gpt-5-mini",
            endpoint="https://api.openai.com/v1/chat/completions",
        )

        result = caller.call(
            system_prompt="system",
            user_input="user",
            max_output_tokens=64,
            timeout_ms=5000,
            trace_name="policy_optimizer.evaluate_policy_effect",
            trace_metadata={
                "thread_id": "metrics-123",
                "feature_name": "policy_optimizer",
                "agent_step_name": "evaluate_policy_effect",
                "environment": "dev",
                "policy_version": "policy-v1",
                "metrics_snapshot_id": "metrics-123",
                "owner_team": "TM_AI",
                "window_start_ms": 100,
                "window_end_ms": 200,
            },
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output_text, "{\"status\":\"LIVE_OK\"}")
        self.assertEqual(result.tokens_in, 21)
        self.assertEqual(result.tokens_out, 9)
        self.assertEqual(result.langsmith_link, {})
        mock_start_trace.assert_called_once()
        self.assertEqual(
            mock_start_trace.call_args.kwargs["metadata"],
            {
                "thread_id": "metrics-123",
                "feature_name": "policy_optimizer",
                "agent_step_name": "evaluate_policy_effect",
                "environment": "dev",
                "policy_version": "policy-v1",
                "metrics_snapshot_id": "metrics-123",
                "owner_team": "TM_AI",
                "window_start_ms": 100,
                "window_end_ms": 200,
            },
        )
        self.assertEqual(
            fake_trace.recorded_usage,
            {"input_tokens": 21, "output_tokens": 9, "total_tokens": 30},
        )
        self.assertIsNotNone(fake_trace.recorded_output)
        self.assertEqual(fake_trace.recorded_errors, [])


if __name__ == "__main__":
    unittest.main()
