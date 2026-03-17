# AI Defense Server: Cloud Team 통합 배포 및 연동 가이드 (Master Guide)

> **대상**: Cloud/Infra 팀 (Deployment, Istio, Authz Adapter 담당)
> **최종 업데이트**: 2026-03-17
> **버전**: v2.0 (V2 실전 엔진 반영)

## 1. 개요
본 문서는 AI Defense Server(V2)를 운영 환경에 배포하고, Istio Envoy Proxy와 연동하기 위한 **모든 요건(CI/CD, 인프라 설정, API 계약)**을 하나로 통합한 마스터 가이드입니다.

---

## 2. 애플리케이션 배포 및 환경 설정

### 2.1. Docker 이미지 빌드
AI 팀이 제공하는 `Dockerfile`을 활용하여 이미지를 빌드합니다. `dev` 브랜치 머지 시 자동 빌드되도록 설정 부탁드립니다.

*   **Dockerfile 위치**: `src/traffic_master_ai/defense/api/Dockerfile` (또는 프로젝트 루트)
*   **엔트리포인트**: `uvicorn traffic_master_ai.defense.api.main:app`
*   **기본 포트**: `8000`

### 2.2. 필수 환경 변수 (Runtime Config)
파드(Pod) 기동 시 아래 변수들을 반드시 주입해 주세요. **특히 Redis는 실전 엔진 가동을 위한 필수 사항입니다.**

| 변수명 | 설명 | 비고 |
| :--- | :--- | :--- |
| `TM_REDIS_URL` | 상태 공유용 Redis 주소 | 예: `redis://redis-svc:6379/0` (필수) |
| `TM_BACKEND_SANCTION_URL` | 백엔드 제재 요청 API | 백엔드 주소 확정 시 주입 (미주입 시 기능만 비활성화됨) |
| `AWS_S3_BUCKET` | Audit 로그 적재용 버킷 | IAM Role 기반 접근 권장 |
| `APP_PORT` | 서버 바인드 포트 | 기본값 `8000` |

---

## 3. 네트워크 및 Istio 연동 명세

### 3.1. 트래픽 검사 경로 (Istio 연동)
모든 실시간 트래픽은 백엔드에 닿기 전 AI 서버의 `/evaluate`를 거쳐야 합니다. 인프라 팀에서는 **Go 기반 Authz Adapter**를 구축하여 아래와 같이 연동해 주세요.

*   **핵심 엔드포인트**: `POST /evaluate` (동기식 판정)
*   **Adapter 로직**: 모든 `POST /api/*` 요청에 대해 AI 서버를 호출하고, 응답의 `allow` 및 `headers_to_add`를 처리합니다.

#### [Istio] VirtualService 설정 (Direct Routing)
VQA 인증이나 행동 분석 데이터 적재(`POST /challenge/*`)는 백엔드를 거치지 않고 AI 서버로 직접 전달되어야 합니다.
```yaml
spec:
  http:
  - match:
    - uri:
        prefix: /challenge/
    route:
    - destination:
        host: ai-defense-service
        port:
          number: 8000
```

#### [Istio] AuthorizationPolicy 설정
```yaml
spec:
  action: CUSTOM
  provider:
    name: ai-defense-authz
  rules:
  - to:
    - operation:
        paths: ["/api/*"]
        notPaths: ["/api/health", "/api/metrics"]
        methods: ["POST"]
```

---

## 4. API 엔드포인트 및 모니터링

### 4.1. 헬스 체크 및 메트릭
*   **Liveness**: `GET /healthz`
*   **Readiness**: `GET /readyz`
*   **모니터링**: `GET /metrics` (Prometheus 연동용)
    *   커스텀 메트릭 `ai_defense_evaluate_total`을 통해 실시간 방어 현황 파악 가능

### 4.2. API 상세 문서 (Swagger)
서버 배포 후 아래 경로에서 상세 스키마를 확인하실 수 있습니다.
*   `GET /docs` (Swagger UI)

---

## 5. 클라우드 팀 체크리스트 (최종)

- [ ] **Redis 준비**: `TM_REDIS_URL` 환경변수 주입 및 통신 확인
- [ ] **Istio 설정**: `AuthorizationPolicy` 및 `VirtualService` 반영
- [ ] **Go Adapter 구축**: AI 서버 `/evaluate` 호출부 구현 및 타임아웃(800ms 권장) 설정
- [ ] **모니터링 연동**: Prometheus에서 `/metrics` 스크래핑 활성화
- [ ] **장애 정책**: AI 서버 장애 시 `fail-open`(트래픽 허용) 처리 확인

---
> [!IMPORTANT]
> **핵심 요약**: 클라우드 팀은 본 문서의 내용을 바탕으로 **이미지 배포, 환경변수 설정, Istio 라우팅** 세 가지만 완수하시면 AI Defense V2 엔진이 즉시 가동됩니다.
