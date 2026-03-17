# AI Defense Server: Cloud Team 통합 배포 및 인프라 가이드 (Master Guide)

> **대상**: Cloud/Infra 팀 (Deployment, Istio, Authz Adapter, Storage 담당)
> **최종 업데이트**: 2026-03-17
> **버전**: v3.0 (Storage/Infra 명세 통합 및 S3·PostgreSQL Phase 2 반영)

### 📌 읽기 가이드

| 구분 | 섹션 | 설명 |
|---|---|---|
| **필독** | §1 저장소 전략 요약 | 전체 아키텍처에서 저장소 역할 분리 |
| **필독** | §2 Docker 빌드 및 환경 변수 | 배포 및  환경변수 전체 목록 |
| **필독** | §3 Redis | MVP 필수 — 코드 준비 완료, 인프라만 필요 |
| **필독** | §4 S3 (Object Storage) | Prod 필수 — AI팀 코드 작성 예정 |
| **필독** | §5 PostgreSQL | Prod 필수 — AI팀 ETL 코드 작성 예정 |
| **필독** | §6 Istio 연동 명세 | Envoy Authz Adapter 설정 |
| **필독** | §7 모니터링 | Prometheus, Swagger |
| **필독** | §8 최종 체크리스트 | Cloud 팀 작업 항목 요약 |

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
                                        │ (prod: 주기적 업로드)
                                        ▼
                                   ┌─────────┐
                                   │   S3     │
                                   │ 아카이빙  │
                                   └────┬────┘
                                        │ ETL (CronJob)
                                        ▼
                                   ┌──────────┐
                                   │PostgreSQL │
                                   │ Analytics │
                                   └──────────┘
```

| 레이어 | 용도 | 저장소 | 단계 |
|---|---|---|---|
| Runtime | 실시간 정책 상태 | **Redis** | MVP 필수 ✅ |
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
| 🔒 계약 | S3 PutObject 권한 | 없으면 업로드 실패 |
| 💡 권장 | Redis 인스턴스 타입·메모리·HA | `redis://` URL만 주면 됨 |
| 💡 권장 | S3 버킷 이름·암호화·Lifecycle | 네이밍/보안 정책은 Cloud팀 자율 |
| 💡 권장 | PG 인스턴스 타입·스토리지·백업 | `postgresql://` URL만 주면 됨 |

---

## 2. Docker 이미지 빌드 및 환경 변수

### 2.1. Docker 이미지 빌드
AI 팀이 제공하는 `Dockerfile`을 활용하여 이미지를 빌드합니다. `dev` 브랜치 머지 시 자동 빌드되도록 설정 부탁드립니다.

*   **Dockerfile 위치**: `src/traffic_master_ai/defense/api/Dockerfile`
*   **빌드 컨텍스트**: 프로젝트 루트 (Root) 권장

```dockerfile
# src/traffic_master_ai/defense/api/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies and include README for metadata generation
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "hatchling" \
    && pip install --no-cache-dir ".[defense_api]"

# Copy source code
COPY src ./src

# Install again to ensure entry points are mapped correctly (if needed by hatch)
RUN pip install --no-cache-dir ".[defense_api]"

# FastAPI 기본 포트
EXPOSE 8000

# 서버 구동 명령
CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2. 환경 변수 전체 목록 (Runtime Config)
파드(Pod) 기동 시 아래 변수들을 Helm chart / ConfigMap / Secret에 설정해 주세요.
전체 변수가 담긴 템플릿 파일: **`.env.ai.example`** (프로젝트 루트)

| 변수명 | 설명 | 기본값 / 비고 |
| :--- | :--- | :--- |
| **[Core]** | | |
| `TM_REDIS_URL` | 실시간 세션 상태 관리용 Redis | `redis://<host>:<port>/<db>` — **비워두면 In-Memory fallback** |
| `TM_BACKEND_SANCTION_URL` | 백엔드 유저 제재(Ban) API 주소 | 비워두면 제재 기능 비활성 |
| **[Storage]** | | |
| `TM_S3_BUCKET` | Audit 로그 아카이빙용 S3 버킷명 | 비워두면 로컬 파일 모드 |
| `TM_S3_PREFIX` | S3 오브젝트 Key prefix | `ai-defense/audit/` |
| `TM_S3_REGION` | S3 버킷 리전 | ap-northeast-2 (기본값) |
| `TM_PG_URL` | PostgreSQL 접속 URL | `postgresql://user:pass@host:5432/db` |
| **[LLM]** | | |
| `TM_OFFLINE_LLM_API_KEY` | 오프라인 최적화용 LLM API Key | OpenAI API Key와 동일 형식 |
| `TM_OFFLINE_LLM_ENDPOINT` | LLM API 엔드포인트 | `https://api.openai.com/v1` |
| `TM_OFFLINE_LLM_MODEL` | 사용할 LLM 모델명 | `gpt-5-mini` |
| **[System]** | | |
| `APP_PORT` | 서버 바인드 포트 | `8000` |
| `CI` | 개발/테스트용 플래그 | **운영 환경에서는 반드시 비워둘 것** (true 설정 시 Redis 미사용 및 In-MemoryFallback) |
| **[Tuning]** | | |
| `TM_T0_MAX` / `TM_T1_MAX` / `TM_T2_MAX` | 위험도 티어 임계치 | 0.20 / 0.50 / 0.80 |
| `TM_TIER_HYSTERESIS_MARGIN` | 히스테리시스 마진 | 0.02 |
| `TM_RISK_ALPHA` | 리스크 가중치 (Alpha) | 0.30 |
| `TM_SESSION_STATE_TTL_SECONDS` | 세션 유지 시간 (초) | 1800 |
| `TM_BLOCK_TTL_SECONDS` | 차단 세션 TTL (초) | 1800 |
| `TM_S3_GRACE_TTL_SECONDS` | VQA 유예 기간 (초) | 180 |
| `TM_POLICY_CACHE_SECONDS` | 정책 캐시 유효 시간 (초) | 5 |
| `TM_CHALLENGE_TTL_SECONDS` | VQA 챌린지 만료 시간 (초) | 15 |
| `TM_CHALLENGE_VERIFY_TIMEOUT_MS` | VQA 검증 타임아웃 (ms) | 200 |
| `TM_CHALLENGE_MAX_ATTEMPTS` | VQA 챌린지 최대 시도 횟수 | 2 |
| `TM_CHALLENGE_HALT_SECONDS` | 초과 시 임시 잠금 시간 (초) | 30 |
| `TM_S3_VERIFY_UNAVAILABLE_MODE` | VQA 불가 시 동작 모드 | `fail_close` |
| `TM_THROTTLE_DELAY_MS_T1` | T1 티어 딜레이 주입 (ms) | 80 |
| `TM_THROTTLE_DELAY_MS_T2` | T2 티어 딜레이 주입 (ms) | 250 |
| `TM_THROTTLE_MAX_DELAY_MS` | 최대 딜레이 제한 (ms) | 2000 |
| `TM_TURNSTILE_ENABLED` | Turnstile 검증 활성화 여부 | `true` |
| `TM_TURNSTILE_VERIFY_TIMEOUT_MS` | Turnstile 검증 타임아웃 (ms) | 500 |
| `TM_TURNSTILE_CACHE_TTL_SECONDS` | Turnstile 결과 캐시 시간 (초) | 600 |
| `TM_DEFENSE_AUDIT_LOG_PATH` | 로컬 Audit 로그 파일 경로 | `logs/defense_decision_audit.jsonl` |

> [!NOTE]
> Tuning 변수(`TM_T0_MAX`, `TM_THROTTLE_*` 등)는 서버 기동 시 초기 기본값으로만 사용됩니다. 운영 중 방어 정책은 오프라인 LLM 최적화 파이프라인이 `PolicySnapshot`을 통해 동적으로 업데이트하므로, 일반적으로 이 값들을 수동으로 변경할 필요는 없습니다.

---

## 3. Redis — MVP 필수 (코드 준비 완료 ✅)

### 3.1 현재 상태
AI Defense 코드에 `RedisStateStore`가 **이미 구현**되어 있습니다. Cloud 팀은 인스턴스만 프로비저닝하면 됩니다.

### 3.2 연결 방식

| 항목 | 값 |
|---|---|
| 환경변수 | `TM_REDIS_URL` |
| 형식 | `redis://<host>:<port>/<db>` |
| 미설정 시 | In-Memory fallback (개발 전용, Pod 간 상태 공유 불가) |
| Python 클라이언트 | `redis>=5.0.0` |
| 서버 호환 버전 | **Redis 6.2 이상** 권장 |

### 3.3 키 패턴 및 데이터

| 항목 | 값 |
|---|---|
| Key pattern | `tm:sess:{sessionId}` |
| TTL | 1800초 (`TM_SESSION_STATE_TTL_SECONDS`로 조정 가능) |
| Value 형식 | JSON (Pydantic model 직렬화) |
| 메모리 추정 | key당 ~1KB → 10만 세션 ≈ 100MB |

```json
{
  "session_id": "sess-abc123",
  "flow_state": "S2",
  "defense_tier": "T0",
  "risk_score": 0.12,
  "challenge_fail_count": 0,
  "policy_version": "v2.0.0-mvp"
}
```

### 3.4 인프라 스펙 권장

| 항목 | 권장값 |
|---|---|
| 인스턴스 타입 | Managed Redis (ElastiCache, Memorystore 등) |
| 메모리 | 최소 256MB (초기), 확장 가능하게 |
| 고가용성 | replica 1개 이상 (failover) |
| 네트워크 | AI Defense Pod와 같은 VPC/네임스페이스 |
| 장기 백업 | 불필요 (runtime cache 성격) |

---

## 4. S3 (Object Storage) — Staging 이상 필요

### 4.1 용도
- Audit log (판정 기록) 아카이빙 — append-only, 불변 증거
- Raw telemetry (VQA 포인터 이벤트) 원본 보존

### 4.2 현재 상태
AI Defense 코드에 `S3Uploader`가 **구현 완료**되어 있습니다. 환경변수(`TM_S3_BUCKET`)가 설정되면 주기적으로 로컬 로그를 S3로 업로드합니다.

### 4.3 환경변수 스펙

| 변수 | 예상값 | 설명 |
|---|---|---|
| `TM_S3_BUCKET` | Cloud팀이 버킷 생성 후 이름 전달 | 버킷 이름 |
| `TM_S3_PREFIX` | `ai-defense/audit/` (AI팀 정의) | 객체 key prefix |
| `TM_S3_REGION` | Cloud팀이 리전 결정 후 전달 | 리전 |
| AWS 인증 | IAM Role / ServiceAccount | Cloud팀이 설정 후 전달 |

> **역할 분담**: AI팀이 env var **이름(스펙)**을 정의하고, Cloud팀이 인프라를 만든 뒤 **값을 채워서** Helm chart에 설정합니다.

### 4.4 업로드 아키텍처

```
판정 발생 → JSONL 파일에 append (즉시, 로컬)
                    │
                    ▼ (주기적 업로드, AI서버 내 백그라운드 워커)
              S3 버킷에 PUT → 업로드 완료 후 로컬 파일 rotate
```

| 항목 | 권장값 |
|---|---|
| 버킷 수 | 1개 (prefix로 audit / telemetry 분리) |
| 보존 정책 | 90일 이상 (감사 증거) |
| 암호화 | SSE-S3 또는 SSE-KMS |
| 접근 권한 | AI Defense Pod의 ServiceAccount에 **PutObject 권한** |
| Lifecycle | 90일 후 Infrequent Access 전환 권장 |

> [!NOTE]
> **Cloud팀 협의 필요**: K8s Pod 재시작 시 로컬 파일이 소실됩니다. 아래 중 하나를 선택해 주세요:
> - **PersistentVolume** 연결: Pod 재시작에도 로그 파일 유지
> - **Sidecar 패턴**: Fluentd 등으로 실시간에 가깝게 S3 전송
> - **짧은 업로드 주기**: 1~5분 간격으로 S3 업로드하여 유실 최소화

---

## 5. PostgreSQL — Staging 이상 필요

### 5.1 용도
- S3의 JSONL → ETL 배치 적재
- KPI 집계, 튜닝 데이터 분석, 리포트 대시보드

### 5.2 현재 상태
ETL 모듈(`etl_worker.py`) **구현 완료**. S3에 적재된 JSONL 데이터를 읽어 DB로 옮기는 작업을 수행합니다. **Cloud팀은 하기 스펙으로 DB 인스턴스만 프로비저닝**해 주세요.

### 5.3 환경변수 스펙

| 변수 | 예상값 | 설명 |
|---|---|---|
| `TM_PG_URL` | `postgresql://<user>:<pass>@<host>:5432/<db>` | 접속 URL |

### 5.4 스키마 방향
- **JSONB 기반**: 판정 로그를 JSONB 컬럼에 저장 (스키마 유연성 확보)
- ETL은 **K8s CronJob** 형태로 실행 예정 (AI팀이 컨테이너 이미지 제공)
- 중복 방지: `trace_id` 기반 Upsert 로직

### 5.5 인프라 스펙 권장

| 항목 | 권장값 |
|---|---|
| 인스턴스 타입 | Managed PostgreSQL (RDS, Cloud SQL 등) |
| 버전 | **PostgreSQL 14 이상** (JSONB 최적화) |
| 스토리지 | 최소 20GB (초기), 자동 확장 |
| 백업 | 일 백업 + PITR (운영 환경) |
| 네트워크 | ETL Job Pod와 같은 VPC |

---

## 6. 네트워크 및 Istio 연동 명세

### 6.1. 전체 트래픽 흐름 (Sequence Diagram)

```mermaid
sequenceDiagram
    participant C as Client (User)
    participant G as Istio / Envoy
    participant A as Authz Adapter (Go)
    participant AI as AI Defense Server
    participant BE as Backend API

    C->>G: API 요청 (e.g. POST /api/payment)
    G->>A: CheckRequest
    A->>AI: POST /evaluate (Session/Path/Method)
    AI-->>A: EvaluateResponse (allow=true, action=NONE)
    A-->>G: OK (+ headers_to_add)
    G->>BE: 원본 요청 전달 (+ x-defense-* headers)
    BE-->>C: 응답 반환
```

### 6.2. 트래픽 검사 경로 및 로직
AI 서버는 실시간 판정과 챌린지 검증이라는 두 가지 핵심 역할을 수행합니다.

#### 1) 실시간 판정 (`POST /evaluate`)
*   **Adapter 로직**: 모든 `POST /api/*` 요청(특히 쓰기 작업)에 대해 AI 서버를 호출하고, 응답의 `allow` 및 `headers_to_add`를 처리합니다.
*   **권장 타임아웃**: 800ms (AI 서버 장애 시 `fail-open` 처리 필수)

#### 2) 챌린지 엔드포인트 (`/challenge/*`)
클라이언트(브라우저)에서 AI 서버로 직접 통신하는 경로입니다. Istio `VirtualService`를 통해 AI 서버로 직접 라우팅되어야 합니다.
*   `POST /challenge/start`: 챌린지 발급
*   `POST /challenge/verify`: 챌린지 결과 검증

---

## 7. API 상세 명세
AI 서버의 고정 인터페이스 정의입니다. 상세 스키마는 서버 기동 후 `/docs`에서 확인할 수 있습니다.

---

### 7.1. 실시간 판정 API (`POST /evaluate`)
Authz Adapter에서 AI 서버로 호출하는 핵심 API입니다.

#### Request Schema
```json
{
  "session_id": "sess-12345",         // [필수] 세션 식별자
  "trace_id": "req-abcd-efgh",        // [권장] 요청 트레이스 ID
  "path": "/api/v1/payment",          // [필수] 대상 API 경로
  "method": "POST",                   // [필수] HTTP 메소드
  "user_id": "user-99",               // [권장] JWT에서 추출한 userId (제재 연동용)
  "timestamp": 1710672000000,         // [필수] 현재 Unix Epoch (ms)
  "headers": {                        // [선택] 필요 시 원본 헤더 전달
    "User-Agent": "Mozilla/5.0..."
  }
}
```

#### Response Schema
```json
{
  "allow": true,                      // [필수] 통과 여부 (false 시 403 차단)
  "session_id": "sess-12345",
  "action": "NONE",                   // [필수] 수행 액션 (NONE, CHALLENGE, THROTTLE, BLOCK)
  "headers_to_add": {                 // [필수] 클라이언트 응답에 추가할 헤더
    "x-defense-tier": "T0",
    "x-defense-action": "none"
  },
  "latency_ms": 15,                   // AI 엔진 처리 소요 시간
  "decision_id": "dec-xyz-789"        // 판정 고유 ID (로그 추적용)
}
```

| 필드 | 설명 | 비고 |
|---|---|---|
| `action` | `NONE` | 정상 트래픽. 추가 조치 없음. |
| `action` | `CHALLENGE` | 봇 의심. 클라이언트에 VQA 챌린지 요구헤더 전송 필요. |
| `action` | `THROTTLE` | 과다 요청. `x-throttle-ms` 만큼 클라이언트 응답 지연 권장. |
| `action` | `BLOCK` | 확정 봇. 즉시 403 Forbidden 처리. |

---

## 8. 모니터링 및 운영

### 8.1. 헬스 체크 및 메트릭
*   **Liveness**: `GET /healthz` (200 OK)
*   **Readiness**: `GET /readyz` (200 OK)
*   **모니터링**: `GET /metrics` (Prometheus Scrapping)
    *   `ai_defense_evaluate_total`: 실시간 판정 통계 (decision label로 차단율 모니터링 가능)

### 8.2. API 상세 문서 (Swagger)
서버 배포 후 아래 경로에서 상세 스키마를 확인하실 수 있습니다.
*   `GET /docs` (Swagger UI)

---

## 9. 클라우드 팀 체크리스트 (최종)

### MVP (즉시)
- [ ] **Redis 인스턴스 프로비저닝**: `TM_REDIS_URL` 환경변수 주입 및 통신 확인
- [ ] **Istio 설정**: `AuthorizationPolicy` 및 `VirtualService` 반영
- [ ] **Go Adapter 구축**: AI 서버 `/evaluate` 호출부 구현 및 타임아웃(800ms) 설정
- [ ] **모니터링 연동**: Prometheus에서 `/metrics` 스크래핑 활성화
- [ ] **장애 정책**: AI 서버 장애 시 `fail-open`(트래픽 허용) 처리 확인

### Staging/Prod (인프라 선행 준비)
- [ ] **S3 버킷 생성**: Lifecycle 정책 설정 (staging/prod 각각)
- [ ] **S3 권한 부여**: AI Defense Pod ServiceAccount에 `PutObject` 권한
- [ ] **PostgreSQL 인스턴스 프로비저닝**: staging/prod 각각
- [ ] **ETL CronJob용 PG 접속 계정 생성**: AI팀이 이미지 제공 예정
- [ ] **확정 env var 수령 후 Helm chart 반영**: `TM_S3_BUCKET`, `TM_PG_URL` 등

---

> [!IMPORTANT]
> **핵심 요약**: **MVP에서는 Redis와 Istio가 필수입니다.** S3와 PostgreSQL은 Staging 이상의 환경에서 판정 기록 보존 및 분석을 위해 필요하며, 모든 연동 코드는 준비되었으므로 환경변수만 주입해주시면 즉시 가동됩니다.
