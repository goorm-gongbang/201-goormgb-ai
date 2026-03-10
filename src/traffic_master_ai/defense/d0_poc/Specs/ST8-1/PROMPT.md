# ST8-1 PROMPT

## Role
Provide one-command local pilot chain for non-LLM stages.

## Hard Rules
- Keep runtime path and offline path separated.
- Do not introduce mandatory LLM/API-key dependency in this chain.

## Implementation Scope
- Add a top-level pilot script chaining ST4 -> ST5(no-key) -> ST7.
- Print output artifact paths for quick verification.

## Required Outputs
- `pilot_step8_no_llm_all.sh`
- end-to-end no-key run evidence
