# ST5-3 PROMPT

## Role
Implement replay dataset builder and batch evaluator for offline defense analysis.

## Hard Rules
- Keep runtime decision path untouched.
- Use log-count/data-driven execution, not fixed time loop.

## Implementation Scope
- Build replay dataset from `decision_audit`.
- Evaluate offline judge results against replay manifest labels.
- Emit metrics summary artifacts for next-stage guardrails.

## Required Outputs
- `step5_build_replay_dataset.py`
- `step5_batch_evaluator.py`
- replay/eval summary files
