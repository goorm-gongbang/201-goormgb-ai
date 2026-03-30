import json
import unittest
from unittest.mock import MagicMock, patch

from traffic_master_ai.defense.backoffice_copilot.adapters.openai import (
    build_openai_review_adapter,
    build_openai_summary_adapter,
)
from traffic_master_ai.defense.backoffice_copilot.core.models import (
    LlmReviewInput,
    SessionAnalysis,
)


class TestBackofficeCopilotOpenAiAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.api_key = "test-api-key"
        self.model = "test-model"

        # Setup standard input formats
        self.session_analysis = SessionAnalysis(
            session_id="sess-1",
            latest_flow_state="F4M",
            latest_action="NONE",
            latest_tier="T1",
            terminal_outcome="NOT_BLOCKED",
            seen_t1=True,
            seen_t2=False,
            vqa_fail_count=0,
            throttle_event_count=0,
            suspicious_signals=["fast_clicks"],
            timeline_summary=["t1: action1", "t2: action2"],
        )
        self.review_input = LlmReviewInput(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            session_analysis=self.session_analysis,
        )

        self.summary_input = {
            "match_id": "match-1",
            "candidate_count": 5,
            "suspicious_count": 2,
        }

    def _mock_urlopen_response(self, content_dict: dict) -> MagicMock:
        mock_response = MagicMock()
        payload = {
            "choices": [{"message": {"content": json.dumps(content_dict)}}]
        }
        mock_response.read.return_value = json.dumps(payload).encode("utf-8")
        
        # We need mock_urlopen to return an object that can be used as a context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_response
        return mock_context_manager

    @patch("urllib.request.urlopen")
    def test_build_openai_review_adapter_success(self, mock_urlopen: MagicMock) -> None:
        expected_output = {
            "review_result": "SUSPICIOUS",
            "evidence_summary": "Test evidence summary",
        }
        mock_urlopen.return_value = self._mock_urlopen_response(expected_output)

        adapter = build_openai_review_adapter(api_key=self.api_key, model=self.model)
        result = adapter(self.review_input)

        self.assertEqual(result, expected_output)
        
        # Verify the request was made correctly
        mock_urlopen.assert_called_once()
        request_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(request_obj.get_header("Authorization"), f"Bearer {self.api_key}")
        
        # Verify prompt structure
        payload = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(payload["model"], self.model)
        messages = payload["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        
        user_content = json.loads(messages[1]["content"])
        self.assertEqual(user_content["session_id"], "sess-1")
        self.assertEqual(user_content["signals"], ["fast_clicks"])

    @patch("urllib.request.urlopen")
    def test_build_openai_summary_adapter_success(self, mock_urlopen: MagicMock) -> None:
        expected_output = {
            "summary_text": ["Line 1", "Line 2", "Line 3"]
        }
        mock_urlopen.return_value = self._mock_urlopen_response(expected_output)

        adapter = build_openai_summary_adapter(api_key=self.api_key, model=self.model)
        result = adapter(self.summary_input)

        self.assertEqual(result, expected_output)
        
        mock_urlopen.assert_called_once()
        request_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(request_obj.get_header("Authorization"), f"Bearer {self.api_key}")

    @patch("urllib.request.urlopen")
    def test_timeout_handled(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = TimeoutError("Simulated timeout")
        
        adapter = build_openai_review_adapter(api_key=self.api_key, model=self.model)
        with self.assertRaises(TimeoutError):
            adapter(self.review_input)

    @patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"Not a JSON string"
        
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_context_manager

        adapter = build_openai_review_adapter(api_key=self.api_key, model=self.model)
        with self.assertRaises(ValueError) as ctx:
            adapter(self.review_input)
            
        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_missing_api_key(self) -> None:
        # Should raise ValueError upfront or when called. Our implementation raises when called.
        adapter = build_openai_review_adapter(api_key="", model=self.model)
        with self.assertRaises(ValueError) as ctx:
            adapter(self.review_input)
        
        self.assertIn("missing API key", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
