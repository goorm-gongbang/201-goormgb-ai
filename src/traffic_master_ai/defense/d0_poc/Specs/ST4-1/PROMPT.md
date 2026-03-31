# ST4-1 PROMPT

## Role
You are implementing ST4-1 in a spec-driven workflow.

## Document Loading Policy
1. Read this file.
2. Read `SPEC_SNAPSHOT.md` and `TEST_PLAN.md` in the same folder.
3. Read current attack agent `graph/nodes.py`, `config.py`, selector contract, and audit usage.

## Hard Rules
- Do not add external LLM/OCR dependencies.
- Keep API contracts unchanged.
- Keep legacy arithmetic flow backward-compatible.

## Implementation Scope
- Add challenge mode config (`pass` / `fail`).
- Extend S3 node to handle catch-ball challenge path deterministically.
- Emit audit events defined in SPEC.

## Required Outputs
- Modified files list
- Test commands executed
- Test results summary
- Risks/known gaps

## PR 메시지 형식
`feat(attack): [ST4-1] challenge bridge for deterministic pass/fail`

## Git 커맨드 형식
```bash
git add .
git commit -m "feat(attack): [ST4-1] challenge bridge for deterministic pass/fail"
git push -u origin <branch-name>
```
