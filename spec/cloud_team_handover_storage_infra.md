# Cloud 팀 인수인계: Storage / Infra 요구사항 명세

> **작성일**: 2026-03-11  
> **작성 팀**: AI Defense 팀  
> **대상**: Cloud/Infra 팀  
> **관련 문서**: `spec/cloud_team_handover_istio_adapter.md` (Adapter 연동 명세)

### 📌 읽기 가이드

| 구분 | 섹션 | 설명 |
|---|---|---|
| **필독** | §1 저장소 전략 요약 | 전체 아키텍처에서 저장소 역할 분리 |
| **필독** | §2 Redis | MVP 필수 — 현재 코드 준비 완료, 인프라만 필요 |
| **필독** | §3 S3 | Prod 필수 — AI팀 코드 작성 예정, 인프라 선행 요청 |
| **필독** | §4 PostgreSQL | Prod 필수 — AI팀 코드 작성 예정, 인프라 선행 요청 |
| **필독** | §6 체크리스트 | Cloud 팀 작업 항목 요약 |
| 참고 | §5 타임라인 | AI팀 ↔ Cloud팀 작업 순서 |

---

## 1. 저장소 전략 요약

```
┌──────────────────────────────────────────────────────────┐
│                    AI Defense Runtime                     │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌───────────────────┐  │
│  │ /evaluate │    │ /challenge│    │ Audit Logger      │  │
│  │ 실시간판정 │    │ VQA 검증  │    │ (판정 기록)       │  │
│  └────┬─────┘    └────┬─────┘    └────┬──────────────┘  │
│       │               │               │                  │
└───────┼───────────────┼───────────────┼──────────────────┘
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐    ┌─────────┐    ┌─────────────┐
   │  Redis   │    │  Redis   │    │  JSONL File  │
   │ 세션상태  │    │ 세션상태  │    │ (로컬 저장)  │
   └─────────┘    └─────────┘    └──────┬──────┘
                                        │ (prod)
                                        ▼
                                   ┌─────────┐
                                   │   S3     │
                                   │ 아카이빙  │
                                   └────┬────┘
                                        │ ETL
                                        ▼
                                   ┌──────────┐
                                   │PostgreSQL │
                                   │ Analytics │
                                   └──────────┘
```

| 레이어 | 용도 | 저장소 | 단계 |
|---|---|---|---|
| Runtime | 실시간 정책 상태 | **Redis** | MVP 필수 |
| Audit 원본 | 불변 판정 증거 | JSONL → **S3** | Staging 이상 |
| Raw Telemetry | VQA 포인터 이벤트 | JSONL → **S3** | Staging 이상 |
| Analytics | KPI/튜닝/리포트 | **PostgreSQL** (JSONB) | Staging 이상 |

### 계약 vs 권장 구분

> 🔒 = AI 코드와 직접 연결되어 **반드시 지켜야** 하는 계약  
> 💡 = Cloud팀이 인프라 정책에 따라 **자율적으로 결정** 가능한 권장사항

| 구분 | 항목 | 이유 |
|---|---|---|
| 🔒 계약 | env var 이름 (`TM_REDIS_URL`, `TM_S3_BUCKET` 등) | 코드에서 이 이름으로 읽음 |
| 🔒 계약 | Redis key 패턴 (`tm:sess:{sessionId}`) | 코드가 이 패턴으로 읽기/쓰기 |
| 🔒 계약 | Redis value JSON 구조 | Pydantic 모델로 직렬화/역직렬화 |
| 🔒 계약 | S3 PutObject 권한 | 없으면 업로드 실패 |
| 💡 권장 | Redis 인스턴스 타입·메모리·HA | `redis://` URL만 주면 됨 |
| 💡 권장 | S3 버킷 이름·암호화·Lifecycle | 네이밍/보안 정책은 Cloud팀 자율 |
| 💡 권장 | PG 인스턴스 타입·스토리지·백업 | `postgresql://` URL만 주면 됨 |
| 💡 권장 | 로그 수집 방식 (PV / Sidecar / 짧은 주기) | Cloud팀이 인프라에 맞게 선택 |

---

## 2. Redis — MVP 필수 (코드 준비 완료 ✅)

### 2.1 현재 상태

AI Defense 코드에 `RedisStateStore`가 **이미 구현**되어 있습니다. Cloud 팀은 인스턴스만 프로비저닝하면 됩니다.

### 2.2 연결 방식

| 항목 | 값 |
|---|---|
| 환경변수 | `TM_REDIS_URL` |
| 형식 | `redis://<host>:<port>/<db>` |
| 미설정 시 | in-memory fallback (개발 전용, Pod 간 상태 공유 불가) |
| Python 클라이언트 | `redis>=5.0.0` (pip, 현재 7.3.0 설치됨) |
| 서버 호환 버전 | **Redis 6.2 이상** 권장 |

### 2.3 키 패턴 및 데이터

| 항목 | 값 |
|---|---|
| Key pattern | `tm:sess:{sessionId}` |
| TTL | 1800초 (환경변수 `TM_SESSION_STATE_TTL_SECONDS`로 조정 가능) |
| Value 형식 | JSON (Pydantic model 직렬화) |
| 예상 key 수 | 동시 세션 수와 비례 (수천~수만) |
| 메모리 추정 | key당 ~1KB → 10만 세션 ≈ 100MB |

주요 필드:
```json
{
  "session_id": "sess-abc123",
  "flow_state": "S2",
  "defense_tier": "T0",
  "risk_score": 0.12,
  "challenge_fail_count": 0,
  "vqa_required": false,
  "vqa_passed": false,
  "vqa_attempt_count": 0,
  "active_challenge_id": null,
  "policy_version": "v2.0.0-mvp"
}
```

### 2.4 인프라 스펙 권장

| 항목 | 권장값 |
|---|---|
| 인스턴스 타입 | Managed Redis (ElastiCache, Memorystore 등) |
| 메모리 | 최소 256MB (초기), 확장 가능하게 |
| 고가용성 | replica 1개 이상 (failover) |
| 네트워크 | AI Defense Pod와 같은 VPC/네임스페이스 |
| 장기 백업 | 불필요 (runtime cache 성격) |

---

## 3. S3 (Object Storage)

### 3.1 용도

- Audit log (판정 기록) 아카이빙 — append-only, 불변 증거
- Raw telemetry (VQA 포인터 이벤트) 원본 보존

### 3.2 현재 상태

현재는 **로컬 JSONL 파일**에만 기록 중 (컨테이너 내부 파일시스템). S3 업로드 코드는 AI팀이 작성 예정이며, 완료 후 환경변수 스펙을 전달드리겠습니다.

### 3.3 예상 환경변수 (확정 후 업데이트)

| 변수 | 예상값 | 설명 |
|---|---|---|
| `TM_S3_BUCKET` | Cloud팀이 버킷 생성 후 이름을 전달 | 버킷 이름 |
| `TM_S3_PREFIX` | `ai-defense/audit/` (AI팀 정의) | 객체 key prefix |
| `TM_S3_REGION` | Cloud팀이 리전 결정 후 전달 | 리전 |
| `AWS_*` or SA | Cloud팀이 IAM/SA 설정 후 전달 | 인증 (IAM Role / ServiceAccount) |

> **역할 분담**: AI팀이 env var **이름(스펙)**을 정의하고, Cloud팀이 인프라를 만든 뒤 **값을 채워서** Helm chart에 설정합니다. (Redis의 `TM_REDIS_URL`과 동일한 패턴)

### 3.4 인프라 스펙 권장

| 항목 | 권장값 |
|---|---|
| 버킷 수 | 1개 (prefix로 audit / telemetry 분리) |
| 일 예상 용량 | 수 GB (트래픽 규모에 비례) |
| 보존 정책 | 90일 이상 (감사 증거) |
| 암호화 | SSE-S3 또는 SSE-KMS |
| 접근 권한 | AI Defense Pod의 ServiceAccount에 PutObject 권한 |
| Lifecycle | 90일 후 Infrequent Access 전환 권장 |

### 3.5 Staging/Prod 업로드 아키텍처

Staging 이상 환경에서는 JSONL 로컬 파일을 **write-ahead buffer**로 사용하고, 주기적으로 S3에 업로드합니다:

```
판정 발생
  │
  ▼
JSONL 파일에 append (즉시, 로컬)
  │
  ▼ (주기적 업로드)
S3 버킷에 PUT (업로드 완료 후 로컬 파일 rotate)
```

| 방식 | 장점 | 단점 |
|---|---|---|
| A. 직접 S3에 PUT (로컬 파일 없음) | 단순 | S3 장애 시 로그 유실 |
| **B. JSONL 로컬 → S3 업로드 (권장)** | S3 장애에도 로컬에 로그 보존 | 로컬 저장 공간 필요 |

> [!NOTE]
> **Cloud팀 협의 필요**: K8s Pod은 재시작 시 로컬 파일이 소실됩니다. 아래 중 하나의 방식을 Cloud팀과 결정해야 합니다:
> - **PersistentVolume** 연결: Pod 재시작에도 로그 파일 유지
> - **Sidecar 패턴**: 로그 수집 sidecar (예: Fluentd)가 실시간에 가깝게 S3로 전송
> - **짧은 업로드 주기**: 1~5분 간격으로 S3 업로드하여 유실 최소화

---

## 4. PostgreSQL

### 4.1 용도

- S3의 JSONL → ETL 적재
- KPI 집계, 튜닝 데이터 분석, 리포트 대시보드

### 4.2 현재 상태

코드 미구현. AI팀이 ETL 모듈을 작성 후 환경변수 스펙을 전달드리겠습니다.

### 4.3 예상 환경변수 (확정 후 업데이트)

| 변수 | 예상값 | 설명 |
|---|---|---|
| `TM_PG_URL` | `postgresql://<user>:<pass>@<host>:5432/<db>` | 접속 URL |

### 4.4 스키마 방향

- **JSONB 기반**: 판정 로그를 JSONB 컬럼에 저장 (스키마 유연성)
- ETL은 **배치 Job** (K8s CronJob) 형태로 실행 예정
- 로그 건수 기반 트리거 (시간 고정 주기가 아닌 데이터 축적 기반)

### 4.5 인프라 스펙 권장

| 항목 | 권장값 |
|---|---|
| 인스턴스 타입 | Managed PostgreSQL (RDS, Cloud SQL 등) |
| 버전 | **PostgreSQL 14 이상** (JSONB 최적화) |
| 스토리지 | 최소 20GB (초기), 자동 확장 |
| 백업 | 일 백업 + PITR (운영 환경) |
| 네트워크 | ETL Job Pod와 같은 VPC |

---

## 5. 타임라인

```
현재 (MVP / dev)
├─ Redis: 코드 완료 ✅ → Cloud팀 인스턴스 프로비저닝만 필요
├─ S3: 로컬 JSONL로 운영
└─ PostgreSQL: 미사용

Staging/Prod 준비 (AI팀 코드 작성 → Cloud팀 인프라 병렬 진행)
├─ AI팀: S3 업로드 코드 + PG ETL 모듈 작성
├─ Cloud팀: S3 버킷 + PG 인스턴스 프로비저닝 (staging/prod 각각)
└─ 완료 후: env var 전달 → staging에서 연동 테스트 → prod 반영
```

---

## 6. Cloud 팀 체크리스트

### MVP (즉시)
- [ ] Redis 인스턴스 프로비저닝
- [ ] AI Defense Helm chart에 `TM_REDIS_URL` 환경변수 설정
- [ ] AI Defense Pod → Redis 네트워크 연결 확인

### Staging/Prod (인프라 선행 준비)
- [ ] S3 버킷 생성 + Lifecycle 정책 설정 (staging/prod 각각)
- [ ] AI Defense Pod ServiceAccount에 S3 PutObject 권한 부여
- [ ] PostgreSQL 인스턴스 프로비저닝 (staging/prod 각각)
- [ ] ETL CronJob용 PG 접속 계정 생성
- [ ] AI팀으로부터 확정 env var 스펙 수령 후 Helm chart 반영

---

> [!IMPORTANT]
> **핵심 요약**: MVP에서는 **Redis만** 필요합니다 (`TM_REDIS_URL` 설정). S3와 PostgreSQL은 **Staging 이상**에서 필요하며, AI팀이 코드를 작성한 뒤 환경변수 스펙을 전달드리겠습니다. Cloud팀은 staging/prod 인프라를 미리 프로비저닝해 주시면 연동이 빨라집니다.
