# Backend Swagger/OpenAPI Enablement Guide

## Why
Backend API도 Swagger(OpenAPI)로 제공해야 FE/AI/Cloud가 같은 계약을 보고 개발할 수 있다.

## Contract vs Tunable
- Fixed: OpenAPI 스펙 형식, 필드명/타입, 버전 관리 원칙.
- Tunable: Swagger endpoint path, 서버 포트, artifact 파일명 suffix.

## Minimum Output
1. Runtime endpoint: `GET /v3/api-docs`
2. Optional UI: `GET /swagger-ui/index.html`
3. Versioned artifact: `openapi-backend.v1.yaml` (CI artifact)

## Step 1: dependency
`/Users/jangjihyeon/201-goormgb-ai/platform/backend/build.gradle`

```gradle
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.8.0'
}
```

## Step 2: (optional) endpoint path config
`/Users/jangjihyeon/201-goormgb-ai/platform/backend/src/main/resources/application.yml`

```yaml
springdoc:
  api-docs:
    path: /v3/api-docs   # baseline
  swagger-ui:
    path: /swagger-ui    # baseline
```

## Step 3: run and verify
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/backend
export TM_BE_PORT=8080
export TM_BE_OPENAPI_PATH=/v3/api-docs
./gradlew bootRun
curl "http://localhost:${TM_BE_PORT}${TM_BE_OPENAPI_PATH}"
```

## Step 4: export artifact for cloud
```bash
curl "http://localhost:${TM_BE_PORT}${TM_BE_OPENAPI_PATH}" -o openapi-backend.v1.json
```

YAML 변환은 CI에서 처리하거나 JSON 그대로 공유해도 OpenAPI 규격상 문제없다.

## Contract Rule
- SSOT 문서 변경 + OpenAPI 변경은 반드시 같은 PR에서 처리
- breaking API는 `v2`로 올리고 하위호환 기간 명시
