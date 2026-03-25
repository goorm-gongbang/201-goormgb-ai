# Istio ext_authz gRPC Adapter

Envoy ext_authz v3 gRPC 프로토콜을 구현한 AI Defense 어댑터입니다.

## 아키텍처

```
┌─────────────────┐     gRPC (9001)      ┌─────────────────────┐     HTTP (8000)      ┌──────────────┐
│  Istio Gateway  │ ──────────────────▶  │  authz-adapter-grpc │ ──────────────────▶  │  AI Defense  │
│  (EnvoyFilter)  │                      │                     │                      │  /evaluate   │
└─────────────────┘                      └─────────────────────┘                      └──────────────┘
```

## 동작 방식

1. Istio IngressGateway의 EnvoyFilter가 Critical API 요청을 감지
2. ext_authz gRPC 호출로 authz-adapter-grpc에 판정 요청
3. authz-adapter-grpc가 AI Defense `/evaluate` 엔드포인트 호출
4. AI Defense 판정 결과를 gRPC 응답으로 반환
5. Envoy가 응답에 따라 요청 허용/차단/챌린지

## 보호 대상 API

| 서비스 | 메서드 | 경로 | 이벤트 타입 |
|--------|--------|------|-------------|
| Queue | POST | `/queue/matches/{id}/enter` | QUEUE_ENTER |
| Seat | GET | `/seat/matches/{id}/recommendations/blocks` | RECOMMENDATION_BLOCKS |
| Seat | POST | `/seat/matches/{id}/recommendations/blocks/{id}/assign` | ASSIGN_HOLD |
| Seat | GET | `/seat/matches/{id}/seat-groups` | SEAT_ENTRY |
| Seat | GET | `/seat/matches/{id}/sections/{id}/blocks` | SECTION_BLOCKS |
| Seat | POST | `/seat/matches/{id}/seat-holds` | SEAT_HOLDS |

## 로컬 실행

```bash
# Docker Compose로 전체 스택 실행
docker-compose up --build

# gRPC 연결 테스트 (grpcurl 필요)
grpcurl -plaintext localhost:9001 list
grpcurl -plaintext localhost:9001 envoy.service.auth.v3.Authorization/Check
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AI_DEFENSE_URL` | `http://ai-defense:8000/evaluate` | AI Defense 엔드포인트 |
| `AI_DEFENSE_TIMEOUT_SEC` | `0.8` | AI Defense 호출 타임아웃 |
| `GRPC_PORT` | `9001` | gRPC 서버 포트 |
| `GRPC_WORKERS` | `10` | gRPC 워커 스레드 수 |
| `TM_AUTHZ_CHECK_METHODS` | `POST,GET` | 체크 대상 HTTP 메서드 |
| `TM_AUTHZ_CHECK_PATH_PREFIXES` | `/queue/,/seat/` | 체크 대상 경로 접두사 |

## 응답 코드

| HTTP 상태 | 의미 | 액션 |
|-----------|------|------|
| 200 | 허용 | 요청 통과 |
| 403 | 차단 | BLOCKED |
| 428 | 챌린지 필요 | CHALLENGE_REQUIRED |

## Kubernetes 배포

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authz-adapter-grpc
  namespace: dev-ai
spec:
  replicas: 2
  selector:
    matchLabels:
      app: authz-adapter-grpc
  template:
    metadata:
      labels:
        app: authz-adapter-grpc
    spec:
      containers:
        - name: authz-adapter-grpc
          image: authz-adapter-grpc:latest
          ports:
            - containerPort: 9001
              protocol: TCP
          env:
            - name: AI_DEFENSE_URL
              value: "http://dev-ai-defense.dev-ai.svc.cluster.local:8000/evaluate"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: authz-adapter-grpc
  namespace: dev-ai
spec:
  selector:
    app: authz-adapter-grpc
  ports:
    - name: grpc
      port: 9001
      targetPort: 9001
      protocol: TCP
```

## 관련 문서

- [Envoy ext_authz](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/auth/v3/external_auth.proto)
- [Istio Authorization Policy](https://istio.io/latest/docs/reference/config/security/authorization-policy/)
