# Defense PoC-0 — D0-4 Spec Snapshot

> **Inherits from:** D0-3 (Acceptance Scenarios)
> **Focus:** Decision Log & Audit Trail

## Inherited Contracts (from D0-1 ~ D0-3)

### State Model
- FlowState: S0 → S1 → S2 → S3 → S4 → S5 → S6 → SX
- DefenseTier: T0 (Normal) → T1 (Suspicious) → T2 (High Risk) → T3 (Attack)

### Event Model
- Canonical Events: FLOW_*, STAGE_*, SIGNAL_*, DEF_*, TIME_*
- Event structure: (event_id, ts_ms, type, source, session_id, payload)

### Brain Components
- SignalAggregator → EvidenceState → RiskController → ActionPlanner → Actuator

### Design Principles
1. Pure Functions: transition(), plan_actions(), decide_tier() are side-effect free
2. Immutable State: Context mutations via dict, EvidenceState via dataclass_replace

---

## D0-4 Purpose

**Goal:** Machine-readable audit trail for every decision made by the Defense Engine.

**Key Schema:** `DecisionLogEntry` captures:
- Event context (type, id, source)
- State/Tier transitions
- Evidence snapshot at decision time
- Planned actions and terminal reasons
