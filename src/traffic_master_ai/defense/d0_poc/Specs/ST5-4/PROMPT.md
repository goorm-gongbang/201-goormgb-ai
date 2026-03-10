# ST5-4 PROMPT

## Role
Implement guardrails that decide whether offline patch candidates are safe to apply.

## Hard Rules
- Never auto-apply policy changes without passing guardrails.
- Manual approval token must be supported.

## Implementation Scope
- Evaluate batch summary + patch candidates.
- Return one decision artifact: `APPLY_READY` or `HOLD`.
- Support strict mode for CI gate.

## Required Outputs
- `guardrails.py`
- `step5_policy_guardrails.py`
- guardrail decision JSON output
