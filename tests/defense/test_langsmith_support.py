import unittest

from traffic_master_ai.defense.langsmith_support import _LangSmithLLMTrace


class _FakeRunTree:
    def __init__(self) -> None:
        self.id = "run-123"
        self.metadata: dict[str, str] = {}
        self.usage_metadata = None
        self.end_calls: list[dict[str, object]] = []

    def get_url(self) -> str:
        return "https://smith.langchain.com/runs/run-123"

    def end(self, *, outputs=None, error=None, **kwargs) -> None:
        self.end_calls.append(
            {
                "outputs": outputs,
                "error": error,
                "extra": kwargs,
            }
        )


class TestLangSmithSupport(unittest.TestCase):
    def test_get_langsmith_link_uses_run_tree_url(self) -> None:
        trace = _LangSmithLLMTrace(
            name="trace-name",
            inputs={},
            metadata={},
        )
        trace._run_tree = _FakeRunTree()

        self.assertEqual(
            trace.get_langsmith_link(),
            {
                "runId": "run-123",
                "traceUrl": "https://smith.langchain.com/runs/run-123",
            },
        )

    def test_record_error_marks_run_failed_on_exit(self) -> None:
        trace = _LangSmithLLMTrace(
            name="trace-name",
            inputs={},
            metadata={},
        )
        fake_run_tree = _FakeRunTree()
        trace._run_tree = fake_run_tree

        trace.record_error("boom")
        trace.__exit__(None, None, None)

        self.assertEqual(trace._error, "boom")
        self.assertEqual(fake_run_tree.metadata["error"], "boom")
        self.assertEqual(len(fake_run_tree.end_calls), 1)
        self.assertEqual(fake_run_tree.end_calls[0]["error"], "boom")
        self.assertIsNone(fake_run_tree.end_calls[0]["outputs"])


if __name__ == "__main__":
    unittest.main()
