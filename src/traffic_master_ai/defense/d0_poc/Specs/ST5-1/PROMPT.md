# ST5-1 PROMPT

## Role
Enforce ACT v2.0 lock: runtime does not use LLM.

## Hard Rules
- Remove runtime LLM decision dependency.
- Keep deterministic policy behavior unchanged.
- Do not break S3 fixed challenge / S6 invariant.

## Implementation Scope
- Remove runtime LLM hooks from evaluate path.
- Remove runtime LLM response/header/audit fields.
- Update docs/specs to reflect "offline-only LLM".
- Re-run deterministic + pilot regression tests.

## Required Outputs
- Updated runtime code
- Updated docs/specs
- Test evidence summary
