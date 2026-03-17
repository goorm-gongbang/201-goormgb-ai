# AI Defense Server: Cloud Team CI/CD & Deployment Guide

## 1. 개요 (Overview)
본 문서는 Hybrid Architecture 확정에 따라, 클라우드/인프라 팀이 **AI Defense Server (Python FastAPI)**를 실제 운영 환경(EKS 등)에 배포하고 Istio Envoy Proxy와 연동하기 위해 필요한 **CI/CD 파이프라인 구성 요건, 컨테이너 빌드 명세, 그리고 API 인터페이스 계약**을 정의합니다.

---

## 2. 애플리케이션 리포지토리 및 빌드 명세

### 2.1. Dockerfile (컨테이너 규격)
AI Defense 서버는 `python:3.12-slim` 베이스 이미지를 사용하며, `uvicorn`을 통해 비동기 웹서버로 구동됩니다.

**소스 트리 위치:** `src/traffic_master_ai/defense/api/` (또는 프로젝트 루트 구조에 따름)

```dockerfile
# Dockerfile.ai-defense
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies and optimize caching
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "hatchling" \
    && pip install --no-cache-dir --no-deps -e ".[defense_api]" \
    || pip install --no-cache-dir fastapi uvicorn redis pydantic

# Copy source code after dependencies are installed
COPY src ./src

# Final installation to ensure all entry points are set correctly
RUN pip install --no-cache-dir ".[defense_api]"

# FastAPI 기본 포트
EXPOSE 8000

# 서버 구동 명령
CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2. CI/CD 환경 변수 요구사항
파드 기동시 주입되어야 할 주요 환경 변수입니다. EKS Secret / ConfigMap으로 마운팅 부탁드립니다.

| Env Variable | Description | Default | 비고 |
| :--- | :--- | :--- | :--- |
| `REDIS_HOST` | 상태 관리를 위한 Redis 클러스터 주소 | `localhost` | Prod 환경 Redis Endpoint 필수 |
| `REDIS_PORT` | Redis 포트 | `6379` | |
| `AWS_S3_BUCKET` | 오프라인 분석용 로그 적재 버킷 | - | IAM OIDC / ServiceAccount Role 바인딩 필요 |
| `TM_S3_VERIFY_UNAVAILABLE_MODE` | VQA 인프라 장애 시 Fallback 정책 | `fail_open` | `fail_open` 권장 |

---

## 3. API 엔드포인트 명세 (L7 라우팅 및 Health Check)

클라우드 팀(Ingress/ALB/Envoy 관점)에서 열어주어야 하거나 모니터링해야 할 엔드포인트 목록입니다. 모든 로직은 단일 포트(`8000`)에서 서빙됩니다.

### 3.1. 프로브 (Liveness / Readiness)
컨테이너 오케스트레이션(K8s) 상태 체크용입니다.
*   `GET /healthz` : 200 OK
*   `GET /readyz` : 200 OK

### 3.2. Istio Envoy ext_authz 연동 엔드포인트
각 트래픽이 백엔드에 닿기 전, Envoy가 동기식으로 호출하여 검사를 수행하는 핵심 엔드포인트입니다.
*   **Endpoint:** `POST /evaluate`
*   **Request Schema (Envoy Adapter -> AI):**
```json
{
  "session_id": "string",
  "path": "string",
  "method": "string",
  "timestamp": 1710500000000,
  "flow_state": "S4",
  "telemetry_features": {
    "tremorStdDev": 0.5,
    "linearityRatio": 0.9,
    "avgVelocity": 120.5
  }
}
```
*   **Response Schema (AI -> Envoy Adapter):**
```json
{
  "allow": true,
  "action": "THROTTLE",
  "headers_to_add": {
    "x-defense-action": "throttle",
    "x-throttle-ms": "300"
  }
}
```

### 3.3. 프론트엔드 직접 통신 엔드포인트 (Backend Bypass 대상)
프론트엔드에서 발생한 트래픽이 **Istio(Ingress Gateway)** 대문을 통과한 후, 백엔드(Spring)로 가지 않고 **AI 서버로 다이렉트 패싱(Direct Forwarding)** 되는 엔드포인트들입니다.

*   `POST /challenge/start` : VQA 캡챠 생성/요청
*   `POST /challenge/verify`: VQA 캡챠 결과 검증
*   `POST /challenge/event` : 마우스 궤적 원본(Raw Telemetry) 비동기 적재

### 3.4. Swagger UI 및 API 전문 (OpenAPI v2)
전체 API 모델 상세 스키마는 Swagger UI를 통해 확인할 수 있습니다. 인프라 설정 시 개발망에만 노출되도록 제한 권장합니다.
*   `GET /docs` (Swagger UI)
*   `GET /openapi.json` (OpenAPI Spec - 런타임에서 자동 생성됨)

---

## 4. 클라우드 인프라 아키텍처 지원 요청 (Action Items)

1.  **Direct Routing (VQA & Telemetry):**
    VQA 인증 팝업이나 행동 수집 등 AI 방어 서버가 직접 처리해야 하는 API 통신(`POST /challenge/*`)은 백엔드(Spring API Gateway)로 라우팅되지 않아야 합니다. **Istio Ingress Gateway 에 `VirtualService` 라우팅 룰을 설정**하여, `/challenge/*` 패스로 들어오는 트래픽은 우리 AI 방어 파드(Service)로 곧장 Forwarding 되도록 터널을 뚫어 주세요.
2.  **IAM / 보안 그룹:** 
    AI 파드가 S3 버킷(로그 적재용)과 ElastiCache Redis에 접근할 수 있도록 권한 정책(Policy) 부여 확인을 요청합니다.
3.  **로드 밸런싱 최적화:** 
    `POST /evaluate`는 모든 트래픽의 병목(Bottleneck)이 될 수 있습니다. gRPC 대신 HTTP REST를 사용하므로 HTTP/2 Keep-Alive 및 Connection Pool 튜닝을 프록시 단에 설정해 주시면 감사하겠습니다.
