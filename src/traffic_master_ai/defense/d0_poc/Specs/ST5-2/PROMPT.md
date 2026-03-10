# ST5-2 PROMPT

## Role
Implement Step5-2 offline LLM analysis path without touching runtime decision behavior.

## Hard Rules
- Runtime `/evaluate` must remain deterministic and unchanged.
- Offline outputs are advisory only (manual review required).
- Trigger condition is log-count based, not fixed time schedule.

## Implementation Scope
- Build offline batch runner for:
  - loading `decision_audit` JSONL
  - session aggregation
  - candidate selection
  - offline judgment (`mock` / `openai_compatible`)
  - policy patch candidate output
- Add tests for:
  - low-log skip path
  - high-risk candidate judgment path

## Required Outputs
- `scripts/step5_offline_llm_batch.py`
- `tests/defense/test_offline_pipeline.py`
- Step5-2 summary/results/patch sample artifacts
