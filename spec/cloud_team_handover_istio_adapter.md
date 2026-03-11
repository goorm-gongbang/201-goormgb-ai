# Cloud 팀 인수인계: Istio ext_authz Adapter + AI Defense 연동 명세

> **작성일**: 2026-03-10  
> **최종 수정일**: 2026-03-11  
> **문서 버전**: v1.1 (환경변수·CI/CD 현황·OpenAPI spec 최신화)  
> **작성 팀**: AI Defense 팀  
> **대상**: Cloud/Infra 팀 (Istio + Authz Adapter 구현 담당)

### 📌 읽기 가이드

| 구분 | 섹션 | 설명 |
|---|---|---|
| **필독** | §3 AI Defense API | 이미지·환경변수·엔드포인트 — Cloud 팀이 배포·연동 시 반드시 알아야 할 계약 |
| **필독** | §4 `/evaluate` API 상세 | Adapter 구현에 필요한 Request/Response 스펙 |
| **필독** | §11 체크리스트 | Cloud 팀 작업 항목 전체 요약 |
| 참고 | §2 아키텍처 | 로컬 파일럿 → K8s 전환 구조도 |
| 참고 | §5~§9 | 파일럿 구현·Istio 설정·Helm 예시 — 자체 구현 시 참고용 |
| 참고 | §10, §12 | 저장소 전략·기존 문서 참조 |

---

## 1. 개요

AI 팀이 **로컬 파일럿** 환경에서 `Envoy ext_authz → Authz Adapter → AI Defense API` 구조를 구현하여 E2E 검증을 마쳤습니다. Cloud 팀은 이 파일럿을 참고하여, **K8s/Istio 환경의 Go 기반 Authz Adapter**와 Helm Chart를 만들면 됩니다.

### 파일럿에서 검증 완료된 항목

- ext_authz HTTP 기반 Check → AI Defense `/evaluate` 호출 → allow/deny 판정
- VQA(Queue Gate) 1회 challenge 필수 경로 (challenge/start → event → verify)
- Envoy deny 시 `x-defense-*` 헤더 전달
- fail-open 정책 (AI Defense 장애 시 트래픽 허용)
- bypass regression 3케이스 검증
- attack agent 실주행 + ext_authz 경유 확인

---

## 2. 아키텍처 (현재 로컬 파일럿)

```
┌─────────────┐     ┌────────────────────┐     ┌───────────────┐     ┌──────────────┐
│  Frontend   │────▶│  Envoy (:10000)    │────▶│ Backend       │     │              │
│  (:3000)    │     │  ext_authz filter  │     │ Spring (:8080)│     │              │
└─────────────┘     └────────┬───────────┘     └───────────────┘     │              │
                             │                                       │   AI Defense │
                             │ ext_authz Check                       │   API        │
                             ▼                                       │   (:8000)    │
                    ┌────────────────────┐      POST /evaluate       │              │
                    │  Authz Adapter     │──────────────────────────▶│              │
                    │  (Python, :9001)   │◀─ allow/deny + headers ──│              │
                    └────────────────────┘                           └──────────────┘
```

### K8s 전환 시 목표 아키텍처

```
┌──────────┐     ┌──────────────────────┐     ┌──────────────┐
│ Client   │────▶│  Istio Sidecar       │────▶│ Backend Pod  │
│          │     │  (Envoy)             │     │              │
└──────────┘     └──────────┬───────────┘     └──────────────┘
                            │ ext_authz gRPC/HTTP
                            ▼
                   ┌────────────────────┐      POST /evaluate
                   │  Authz Adapter     │──────────────────▶┌──────────────┐
                   │  (Go, gRPC :9001)  │◀── JSON response──│ AI Defense   │
                   │  K8s Deployment    │                   │ API Pod      │
                   └────────────────────┘                   │ (:8000)      │
                                                            └──────────────┘
```

---

## 3. AI Defense API — Cloud 팀이 알아야 할 것

### 3.1 이미지 & 실행

CI/CD 파이프라인이 `dev` 브랜치 merge 시 자동으로 Docker 이미지를 빌드·push합니다.  
(Dockerfile은 AI 팀이 제공, CI/CD 파이프라인은 Cloud 팀이 구축 완료.)

| 항목 | 값 |
|---|---|
| Dockerfile | `spec/delivery_bundle_2026-03-04/CI/Dockerfile.ai-defense` |
| 엔트리포인트 | `uvicorn traffic_master_ai.defense.api.main:app` |
| 기본 포트 | `8000` (`APP_PORT` 환경변수로 변경 가능) |
| OpenAPI Spec | `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v2.yaml` |

### 3.2 환경 변수

**서버 바인드** (Dockerfile CMD에서 사용):

| 변수 | 기본값 | 설명 |
|---|---|---|
| `APP_PORT` | `8000` | 바인드 포트 (Dockerfile CMD에서 `--port ${APP_PORT}`) |

> 호스트는 `0.0.0.0`으로 Dockerfile에 하드코딩되어 있습니다.

**런타임 설정** (Python 코드에서 `os.getenv()`로 읽음):

| 변수 | 기본값 | 설명 |
|---|---|---|
| `TM_REDIS_URL` | (빈 문자열) | 설정 시 Redis 사용, 미설정 시 in-memory fallback |
| `TM_SESSION_STATE_TTL_SECONDS` | `1800` | 세션 상태 TTL (초) |
| `TM_DEFENSE_POLICY_VERSION` | `v2.0.0-mvp` | 정책 버전 태그 |
| `TM_DEFENSE_AUDIT_LOG_PATH` | `logs/defense_decision_audit.jsonl` | 감사 로그 경로 |

> [!NOTE]
> K8s 배포 시에는 `TM_REDIS_URL=redis://<host>:6379/0`을 반드시 설정하세요.  
> 로컬 개발 시에는 미설정으로 in-memory 모드로 동작합니다.  
> 전체 환경변수 목록은 `.env.ai.example` 참고.

### 3.3 엔드포인트 목록

| Method | Path | 용도 |
|---|---|---|
| `GET` | `/healthz` | Liveness |
| `GET` | `/readyz` | Readiness |
| `POST` | `/evaluate` | **핵심** — Adapter가 호출하는 실시간 판정 |
| `POST` | `/challenge/start` | VQA 챌린지 발급 |
| `POST` | `/challenge/event` | VQA 포인터 이벤트 수집 |
| `POST` | `/challenge/verify` | VQA 챌린지 검증 |
| `GET` | `/runtime/{session_id}` | 세션 런타임 상태 조회 |
| `POST` | `/runtime/vqa/mark` | VQA 통과 마크 (Backend → AI Defense 동기화) |
| `GET` | `/meta/storage` | 저장소 메타 정보 |

---

## 4. `/evaluate` API 상세 — Adapter 구현에 필요한 계약

### 4.1 Request (Adapter → AI Defense)

```json
{
  "session_id": "sess-abc123",           // 필수
  "trace_id": "trc-xxx",                 // 선택 (추적용)
  "path": "/api/seats/hold",             // 필수 — 원본 요청 경로
  "method": "POST",                      // 필수 — HTTP 메소드
  "timestamp": 1772500000000,            // 필수 — Unix epoch ms
  "headers": {                           // 선택
    "user-agent": "...",
    "x-forwarded-for": "..."
  },
  "flow_state": "S2",                    // 선택 — 현재 플로우 상태
  "defense_tier": "T0",                  // 선택 — 현재 방어 등급
  "challenge_fail_count": 0,             // 선택 — 챌린지 실패 횟수
  "repetitive_pattern_count": 0,         // 선택 — 반복 패턴 카운트
  "token_mismatch": false,               // 선택 — 토큰 불일치 여부
  "telemetry_features": {                // 선택 — 텔레메트리 피처
    "totalDist": 450.2,
    "linearDist": 220.1,
    "linearityRatio": 0.489,
    "avgVelocity": 1.2,
    "tremorStdDev": 0.03,
    "dwellTime": 320
  }
}
```

### 4.2 Response (AI Defense → Adapter)

**허용 시 (HTTP 200):**
```json
{
  "allow": true,
  "session_id": "sess-abc123",
  "flow_state": "S5",
  "defense_tier": "T0",
  "action": "NONE",
  "actions": ["NONE"],
  "reason": null,
  "rule_hits": [],
  "risk_score": 0.12,
  "policy_version": "def-pol-2.0.0",
  "headers_to_add": {
    "x-defense-policy-version": "def-pol-2.0.0",
    "x-defense-tier": "T0",
    "x-defense-action": "none",
    "x-defense-actions": "none"
  },
  "decision_id": "dec-a1b2c3d4e5f6",
  "latency_ms": 3,
  "version": "v2"
}
```

**차단/챌린지 시 (HTTP 403/428):**
```json
{
  "allow": false,
  "session_id": "sess-abc123",
  "flow_state": "S3",
  "defense_tier": "T2",
  "action": "CHALLENGE",
  "actions": ["CHALLENGE"],
  "reason": "VQA_NOT_PASSED",
  "rule_hits": ["REQUIRE_S3"],
  "risk_score": 0.65,
  "policy_version": "def-pol-2.0.0",
  "headers_to_add": {
    "x-defense-action": "challenge",
    "x-defense-tier": "T2",
    "x-challenge-required": "true",
    "x-challenge-type": "queue_gate",
    "x-defense-policy-version": "def-pol-2.0.0"
  },
  "decision_id": "dec-f6e5d4c3b2a1",
  "latency_ms": 5,
  "version": "v2"
}
```

### 4.3 Action 종류 & HTTP 상태 매핑

| Action | 의미 | Adapter HTTP 응답 코드 |
|---|---|---|
| `NONE` | 허용 | 200 (Envoy upstream 전달) |
| `CHALLENGE` | VQA 챌린지 필요 | **428** (Precondition Required) |
| `THROTTLE` | 속도 제한 | 200 + `x-throttle-ms` 헤더 |
| `GATE` | 고가치 행위 게이트 | **428** |
| `BLOCK` | 차단 | **403** |

---

## 5. Authz Adapter — 로컬 파일럿 구현 참고

현재 파일럿의 Adapter는 Python(FastAPI)으로 되어 있습니다. Cloud 팀은 이를 **Go ext_authz gRPC 서비스**로 재구현합니다.

### 5.1 핵심 로직 (Python → Go 변환 포인트)

파일럿 코드: `pilot/istio_adapter_local/adapter/main.py`

```
1. 요청 수신 (Envoy ext_authz Check)
2. 원본 경로/메소드 추출
   - x-envoy-original-path 또는 :path 헤더 → path
   - x-original-method 또는 :method 헤더 → method
3. 체크 대상 판별
   - method가 CHECK_METHODS에 포함 (기본: POST)
   - path가 CHECK_PATH_PREFIXES로 시작 (기본: /api/)
   - 미해당 시 → 즉시 200 반환 (skip)
4. AI Defense /evaluate 호출
   - payload 구성 (session_id, path, method, timestamp, headers 등)
   - timeout: 800ms
5. 판정 결과 처리
   - allow=true → 200 + headers_to_add 전달
   - allow=false, action=CHALLENGE → 428 + CHALLENGE_REQUIRED
   - allow=false, action=GATE → 428 + HIGH_VALUE_GATED
   - allow=false, action=BLOCK → 403 + BLOCKED
6. 장애 시 → fail-open (200 반환)
```

### 5.2 Adapter 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AI_DEFENSE_URL` | `http://ai-defense:8000/evaluate` | AI Defense API 엔드포인트 |
| `AI_DEFENSE_TIMEOUT_MS` | `800` | 호출 타임아웃 (ms) |
| `ADAPTER_POLICY_VERSION` | `adapter-v1` | Adapter 정책 버전 태그 |
| `TM_AUTHZ_CHECK_METHODS` | `POST` | 체크 대상 HTTP 메소드 (쉼표 구분) |
| `TM_AUTHZ_CHECK_PATH_PREFIXES` | `/api/` | 체크 대상 경로 프리픽스 (쉼표 구분) |

### 5.3 Fail-Open 정책

AI Defense 호출 실패 시 (timeout, 5xx, 연결 불가 등):
- **트래픽을 허용**합니다 (fail-open)
- 응답 헤더에 `x-defense-adapter: fail-open` 추가

---

## 6. Envoy ext_authz 설정 — Istio 전환 시 참고

### 6.1 로컬 파일럿 Envoy 설정

파일럿 설정: `pilot/istio_adapter_local/envoy/envoy.yaml`

**전달해야 할 요청 헤더:**
```yaml
authorization_request.allowed_headers:
  - x-session-id         # 세션 식별 (필수)
  - x-trace-id           # 추적 ID
  - user-agent           # UA 분석
  - x-forwarded-for      # 클라이언트 IP
  - cookie               # 세션 쿠키
  - x-flow-state         # 현재 플로우 상태
  - x-defense-tier       # 현재 방어 등급
  - x-repetitive-pattern-count
  - x-challenge-fail-count
  - x-token-mismatch
  - :path                # 원본 경로 (Envoy pseudo-header)
  - :method              # 원본 메소드 (Envoy pseudo-header)
```

**업스트림으로 전달할 응답 헤더:**
```yaml
authorization_response.allowed_upstream_headers:
  - prefix: x-defense-    # 모든 x-defense-* 헤더
  - exact: x-throttle-ms
  - exact: x-gate-mode
```

**클라이언트로 전달할 응답 헤더 (deny 시):**
```yaml
authorization_response.allowed_client_headers:
  - prefix: x-defense-
  - exact: x-throttle-ms
  - exact: x-gate-mode
  - exact: x-block-reason
```

### 6.2 Istio MeshConfig 전환

```yaml
# 로컬 파일럿에서는 ext_authz HTTP service를 사용하지만,
# Istio에서는 envoyExtAuthz gRPC를 권장합니다.
extensionProviders:
- name: ai-defense-authz
  envoyExtAuthz:
    service: authz-adapter.security.svc.cluster.local
    port: 9001
    includeRequestHeadersInCheck:
    - x-session-id
    - cookie
    - user-agent
    - x-forwarded-for
    - x-flow-state
    - x-defense-tier
    - x-repetitive-pattern-count
    - x-challenge-fail-count
    - x-token-mismatch
    headersToDownstreamOnDeny:
    - x-defense-action
    - x-block-reason
    - x-defense-tier
    - x-defense-policy-version
    - x-challenge-required
    - x-challenge-type
    - x-throttle-ms
```

### 6.3 AuthorizationPolicy

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: ai-defense-check
  namespace: default
spec:
  selector:
    matchLabels:
      app: backend
  action: CUSTOM
  provider:
    name: ai-defense-authz
  rules:
  - to:
    - operation:
        paths: ["/api/*"]
        notPaths: ["/api/health", "/api/metrics", "/api/games/*"]
        methods: ["POST"]
```

> [!NOTE]
> `notPaths`에 `/api/games/*`도 추가했습니다. 현재 파일럿에서는 `TM_AUTHZ_CHECK_METHODS=POST`로 GET을 걸러내고 있지만, Istio AuthorizationPolicy에서 명시적으로 제외하는 것이 안전합니다.

---

## 7. x-defense-* 헤더 전체 목록

| 헤더 | 방향 | 설명 |
|---|---|---|
| `x-defense-action` | AI → Adapter → Client/Backend | `none`, `challenge`, `throttle`, `gate`, `block` |
| `x-defense-actions` | AI → Adapter → Backend | 동일 (배열 호환용) |
| `x-defense-tier` | AI → Adapter → Client/Backend | `T0`, `T1`, `T2`, `T3` |
| `x-defense-policy-version` | AI/Adapter → Client/Backend | 정책 버전 태그 |
| `x-defense-trace-id` | Adapter → Backend | 추적 ID 패스스루 |
| `x-defense-adapter` | Adapter → Client | `fail-open` (장애 시) |
| `x-defense-check-skipped` | Adapter → Backend | 체크 스킵 시 `true` |
| `x-challenge-required` | AI → Client | `true` (challenge 필요 시) |
| `x-challenge-type` | AI → Client | `queue_gate` |
| `x-block-reason` | AI → Client | 차단 사유 |
| `x-throttle-ms` | AI → Backend | 쓰로틀 지연 (ms) |
| `x-gate-mode` | AI → Backend | 게이트 모드 |

---

## 8. 로컬 파일럿 파일 목록 (참고용)

| 파일 | 설명 |
|---|---|
| `pilot/istio_adapter_local/adapter/main.py` | Adapter 핵심 로직 (Python FastAPI) |
| `pilot/istio_adapter_local/adapter/Dockerfile` | Adapter 컨테이너 |
| `pilot/istio_adapter_local/envoy/envoy.yaml` | Envoy ext_authz 설정 |
| `pilot/istio_adapter_local/docker-compose.yml` | 3-서비스 스택 구성 |
| `pilot/istio_adapter_local/pilot_check.sh` | 헬스체크 + ext_authz 경유 검증 |
| `pilot/istio_adapter_local/NOTION_LOCAL_PILOT_ARCHITECTURE.md` | 아키텍처 다이어그램 |

---

## 9. Helm Chart 구성 가이드

### 9.1 authz-adapter Chart

```yaml
# values.yaml 핵심 항목
replicaCount: 2

image:
  repository: <registry>/authz-adapter
  tag: latest

service:
  port: 9001        # gRPC
  type: ClusterIP

env:
  AI_DEFENSE_URL: "http://ai-defense.security.svc.cluster.local:8000/evaluate"
  AI_DEFENSE_TIMEOUT_MS: "800"
  TM_AUTHZ_CHECK_METHODS: "POST"
  TM_AUTHZ_CHECK_PATH_PREFIXES: "/api/"

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi
```

### 9.2 ai-defense Chart

```yaml
# values.yaml 핵심 항목
replicaCount: 2

image:
  repository: <registry>/ai-defense
  tag: latest

service:
  port: 8000
  type: ClusterIP

env:
  APP_PORT: "8000"
  TM_REDIS_URL: "redis://redis-svc:6379/0"   # K8s에서는 Redis 필수
  TM_SESSION_STATE_TTL_SECONDS: "1800"
  TM_DEFENSE_POLICY_VERSION: "v2.0.0-mvp"
  TM_DEFENSE_AUDIT_LOG_PATH: "logs/defense_decision_audit.jsonl"

resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi
```

---

## 10. 저장소 전략 요약

| 레이어 | 용도 | 저장소 | 비고 |
|---|---|---|---|
| Runtime | 실시간 정책 상태 | Redis | TTL 1800s, key: `tm:sess:{sessionId}` |
| Audit 원본 | 불변 판정 증거 | JSONL + Object Storage | append-only |
| Raw Telemetry | VQA 포인터 이벤트 | JSONL + Object Storage | 고용량 원본 |
| Analytics | KPI/튜닝/리포트 | PostgreSQL (JSONB) | ETL 적재 |

상세: `spec/delivery_bundle_2026-03-04/CI/storage_strategy.md`

---

## 11. Cloud 팀 체크리스트

- [ ] Go ext_authz gRPC Adapter 구현 (§5 참고)
- [ ] AI Defense Docker 이미지 K8s 배포 (§3 참고)
- [ ] Istio MeshConfig에 extensionProvider 등록 (§6.2)
- [ ] AuthorizationPolicy 적용 (§6.3)
- [ ] Helm Chart 작성 (§9)
- [ ] Redis 인스턴스 프로비저닝 (`TM_REDIS_URL=redis://<host>:6379/0`)
- [ ] ext_authz 경유 E2E 테스트 (§8 `pilot_check.sh` 참고)
- [ ] fail-open 동작 확인 (AI Defense 다운 시 트래픽 허용)
- [ ] x-defense-* 헤더 전달 확인 (Frontend/Backend 연동)
- [ ] `/healthz`, `/readyz` liveness/readiness probe 설정

---

## 12. 기존 전달 문서 참조

| 문서 | 경로 |
|---|---|
| OpenAPI v2 Spec | `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v2.yaml` |
| Defense API README | `spec/delivery_bundle_2026-03-04/CI/defense_api_README.md` |
| 저장소 전략 | `spec/delivery_bundle_2026-03-04/CI/storage_strategy.md` |
| Cloud/BE 협업 체크리스트 | `spec/delivery_bundle_2026-03-04/CI/cloud_backend_collaboration_checklist.md` |
| 전달 번들 README | `spec/delivery_bundle_2026-03-04/README.md` |

---

> [!IMPORTANT]
> **핵심 요약**: Cloud 팀은 AI Defense API를 **블랙박스로 취급**하면 됩니다. Adapter에서 `/evaluate`만 호출하고, 응답의 `allow`/`action`/`headers_to_add`를 그대로 Envoy 응답에 매핑하세요. AI Defense Docker 이미지는 CI/CD 파이프라인(`dev` 브랜치 merge)을 통해 자동 빌드·push됩니다.
