# D0-MVP Spec Implementation Matrix

Status legend:
- `Implemented`: runtime/module behavior exists and is wired.
- `Implemented (Local MVP)`: implemented with local-file or stubbed MVP path.
- `Partial`: core contract exists, but a production-grade variant is still missing.
- `Doc/Governance`: authoritative doc resolved via code + SSOT alignment.

| # | Spec Doc | Status | Notes |
|---|---|---|---|
| 1 | `ssot_specs/L0/l0_core.yaml` | Implemented | Flow state, reasonCode, headers, audit minimum schema enforced in runtime/orchestrator/models. |
| 2 | `ssot_specs/L0/l0_defense_policy.yaml` | Implemented | EWMA, thresholds, hysteresis, probation, passive decay wired into `Guard` and `Planner`. |
| 3 | `ssot_specs/L0/l0_sdd_guide.yaml` | Doc/Governance | Implementation follows spec-driven package layout and runtime separation. |
| 4 | `ssot_specs/L1/llm/defense_llm_ssot.yaml` | Implemented | Offline evaluator/summarizer, circuit breaker, budgets, allowlist, audit logging, OpenAI-compatible REST caller path implemented with stub fallback. |
| 5 | `ssot_specs/L1/runtime/actuators.yaml` | Implemented | Throttle, block, challenge actions wired; S3 PASS keeps `s3Passed` and transitions on next request. |
| 6 | `ssot_specs/L1/runtime/contracts.yaml` | Implemented | `/evaluate`, `/check`, challenge endpoints, error schema, `X-Turnstile-Token` header priority with body fallback. |
| 7 | `ssot_specs/L1/runtime/events.yaml` | Implemented | Runtime event validation + audit catalog including invalid transition, challenge, turnstile events. |
| 8 | `ssot_specs/L1/runtime/index.yaml` | Doc/Governance | Runtime path and audit requirements align with shipped modules. |
| 9 | `ssot_specs/L1/runtime/logic.yaml` | Implemented | Guard -> Analyzer -> Planner -> Orchestrator flow and fixed S3 gate enforced. |
| 10 | `ssot_specs/L1/runtime/open_question.yaml` | Implemented | MVP-relevant open items resolved to `DECIDED`; deferred non-MVP items remain deferred only. |
| 11 | `ssot_specs/L1/runtime/state.yaml` | Implemented | Writer responsibility, TTL, grace-period, block key, state schema enforced by session/block managers. |
| 12 | `ssot_specs/L2/obs_opt/defense_admin_console_ssot.yaml` | Implemented | Read-only admin REST, session drilldown, integrity/policy views, HTML control-room UI, and role+token access control implemented. |
| 13 | `ssot_specs/L2/obs_opt/defense_observability_ssot.yaml` | Implemented (Local MVP) | decision_audit, collector, local warehouse, dedup-aware aggregation, KPI queries, and 7-day local retention purge implemented. |
| 14 | `ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml` | Implemented (Local MVP) | Metrics collection, proposal validation, canary/expand/rollback, persisted rollout state implemented locally. |
| 15 | `ssot_specs/L2/obs_opt/policy_v1.yaml` | Implemented | Policy snapshot/load/store/rollout assignment and mutable local policy storage implemented. |
| 16 | `ssot_specs/annex/analyzer_spec.yaml` | Implemented | Evidence counters, derived signals, planner summary generation wired in runtime. |
| 17 | `ssot_specs/annex/block_spec.yaml` | Implemented | Separate block key, terminal-first enforcement, TTL, audit events wired. |
| 18 | `ssot_specs/annex/challenge_spec.yaml` | Implemented | Fixed S3 issue/verify, fail/open path, cooldown, halt, audit issue/result/halted wired. |
| 19 | `ssot_specs/annex/guard_spec.yaml` | Implemented | Internal/external score fusion, EWMA, passive decay, probation-aware tiering implemented. |
| 20 | `ssot_specs/annex/orchestrator_spec.yaml` | Implemented | Terminal-first, transition validation, S3 hard gate, commit/deny shaping, invalid transition audit wired. |
| 21 | `ssot_specs/annex/planner_spec.yaml` | Implemented | Policy-driven action matrix, evidence summary reasoning, S3 gate, deny mapping implemented. |
| 22 | `ssot_specs/annex/throttle_spec.yaml` | Implemented | Path scoping, delay resolution, `/check` adapter enforcement, throttle audit implemented. |
| 23 | `ssot_specs/annex/turnstile_spec.yaml` | Implemented | Trigger budget/cooldown, verify normalization, fail-open, cache, trigger/verify audit implemented. |

## Current interpretation
- Runtime/L1/annex scope is implemented end-to-end.
- L2 observability/optimization/admin scope is implemented as a local-file MVP path inside the repo.
- External systems are still env-driven integrations, but the SSOT-defined code paths now exist in-repo.
