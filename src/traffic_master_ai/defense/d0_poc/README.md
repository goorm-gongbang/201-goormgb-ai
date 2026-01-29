# Defense D0-PoC — Structural Placeholder

> **⚠️ This directory is a structural placeholder for PoC-0 phase.**

## Purpose

이 디렉토리는 PoC-0 단계에서 **구조적 placeholder** 역할만 수행합니다.  
실제 방어 로직은 PoC-1 이후에 구현될 예정입니다.

## Directory Structure

```
defense/d0_poc/
├── orchestrator/   # Defense Orchestrator (empty)
├── policy/         # Policy Manager (empty)
├── signals/        # Defense signal/event schemas (empty)
├── actions/        # DEF_* enforcement action definitions (empty)
└── README.md       # This file
```

## Naming Convention
- **Attack PoC-0**: `traffic_master/attack/a0_poc/`
- **Defense PoC-0**: `traffic_master/defense/d0_poc/`

## Current Status: PoC-0 (Local Mock)

- 구조와 계약(contract)만 정의됨
- 실제 런타임 로직 없음
- Attack 영역과 동일한 Semantic Event 계약 공유

## Non-Goals (PoC-0)

이 단계에서 구현하지 **않는** 항목:

- ❌ Risk Engine 구현
- ❌ ML 기반 이상 탐지
- ❌ Rule 기반 판단 로직
- ❌ 실시간 Enforcement
- ❌ LLM/AI 의사결정

## Related

- Attack Engine: `traffic_master/attack/a0_poc/`
- Common Contracts: `traffic_master/common/contracts/`
