# Traffic Master AI (201-goormgb-ai)

Traffic Master 프로젝트의 AI 도메인 레포지토리입니다.

> 📦 **Package**: `traffic_master_ai`

## Multi-Repo 전략

이 레포는 goorm-gongbang organization의 멀티레포 구조 중 AI 파트입니다.

| 레포 | 역할 |
|------|------|
| **201-goormgb-ai** | AI 도메인 (현재 레포) |
| 101-goormgb-frontend | 프론트엔드 |
| 102-goormgb-backend | 백엔드 (Java) |
| 301-goormgb-terraform | Infrastructure as Code |
| 302-goormgb-k8s | Kubernetes 설정 |
| 303-goormgb-k6 | 부하 테스트 |

## Directory Structure

```
src/traffic_master_ai/
├── attack/
│   └── a0_poc/          # Attack PoC-0 (State Machine Engine)
├── defense/
│   └── d0_poc/          # Defense PoC-0 (Placeholder)
└── common/
    ├── events/          # Shared event types
    ├── states/          # S0~SX state definitions
    └── contracts/       # Attack ↔ Defense interface
```

## A0/D0 Naming Convention

| Domain  | PoC-0 Path                            |
|---------|---------------------------------------|
| Attack  | `traffic_master_ai/attack/a0_poc/`    |
| Defense | `traffic_master_ai/defense/d0_poc/`   |

## Quick Start

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -q

# Type check
mypy src/

# Lint
ruff check src/
```
