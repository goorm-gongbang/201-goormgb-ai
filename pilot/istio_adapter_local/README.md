# Local Pilot: Istio(ext_authz)-style Envoy + Authz Adapter + AI Defense

이 구성은 K8s/Istio를 로컬에서 바로 재현하기 위한 파일럿입니다.

노션 공유용 다이어그램/설명은 `NOTION_LOCAL_PILOT_ARCHITECTURE.md` 참고.

## 구성
- Envoy (port 10000): API 프록시 + ext_authz 필터
- Authz Adapter (port 9001): Envoy ext_authz HTTP 서비스
- AI Defense API (port 8000): `/evaluate` 판정
- Backend(Spring): host에서 `localhost:8080`로 실행
- Frontend(Next): host에서 실행, API rewrite target을 Envoy로 지정

## 1) Backend 실행 (host)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/backend
./gradlew bootRun
```

## 2) Envoy/Adapter/AI 실행 (docker-compose)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose up -d --build
```

## 3) Frontend 실행 (Envoy 경유)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/frontend
TM_API_PROXY_TARGET=http://localhost:10000 npm run dev
```

## 4) 헬스체크
```bash
curl -sS http://localhost:8000/healthz
curl -sS http://localhost:9001/healthz
curl -sS http://localhost:9901/server_info
curl -sS -H 'x-session-id:sess-pilot-1' http://localhost:10000/api/queue/enter -X POST -H 'content-type:application/json' -d '{"gameId":"game-001"}'
```

## 5) Attack Agent 테스트
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
TM_FRONTEND_URL=http://localhost:3000 python -m traffic_master_ai.attack.a1_mvp.main --mode MAP
```

## 6) Step3 일괄 검증 (유저 성공 + 공격 차단)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
./pilot_step3_e2e.sh
```

검증 포함 항목:
- 유저 경로: `POST /api/booking/entry` -> `428 CHALLENGE_REQUIRED`
- 백엔드 VQA 검증 성공 후 재시도: `POST /api/booking/entry` -> `200`
- AI runtime 동기화 확인: `/runtime/{session}` 에서 `vqa_passed=true`
- 공격자 유사 경로(무 solver): challenge 실패 누적으로 차단 확인
- (옵션) 실제 Attack Agent 실행: `playwright` 설치된 경우에만 자동 실행

## 6-1) Step4-2 실주행 검증 (Envoy/ext_authz 경유 + MAP DONE)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step4_st2_e2e.sh
```

검증 포함 항목:
- attack-agent `MAP` 모드 실주행 완료 (`terminal_reason=DONE`)
- 공격 로그 필수 이벤트 확인 (`ENTRY_CLICKED`, `QUEUE_PASSED`, `CHALLENGE_PASSED`, `HOLD_ACQUIRED`, `PAYMENT_COMPLETED`)
- adapter 로그에서 ext_authz 경유 확인 (`/check/api/holds`, `/check/api/payments`)

## 6-2) Step4-3 지표/회귀 검증 (strict gate)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
./pilot_step4_st3_metrics.sh
```

검증 포함 항목:
- bypass regression 3케이스 (`NO_EVENTS`, `IMPOSSIBLE_SPEED`, `TOKEN_BINDING_MISMATCH`)
- metrics strict gate pass/fail 판정
- 출력 파일 생성: `logs/step4/st4_3_metrics_report.json`

## 6-3) Step4 전체 체인 일괄 실행
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step4_all.sh
```

검증 포함 항목:
- ST4-2 실주행 완료 + ext_authz 경유 확인
- ST4-3 metrics strict gate 통과
- ST4-4 bypass regression 3케이스 통과

## 6-4) Step5 no-key 체인 (오프라인 분석 + 가드레일)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
./scripts/step5_no_key_all.sh
```

산출물:
- `logs/step5_replay_dataset.jsonl`
- `logs/step5_replay_manifest.json`
- `logs/step5_batch_eval_summary.json`
- `logs/step5_policy_apply_decision.json`

LLM 실호출 모드(키 필요):
```bash
cd /Users/jangjihyeon/201-goormgb-ai
export TM_OFFLINE_LLM_API_KEY="<your_api_key>"
export TM_OFFLINE_LLM_MODE="openai_compatible"
# 선택: 수동 승인 토큰
export TM_POLICY_APPLY_APPROVAL_TOKEN="<manual_approval_token>"
./scripts/step5_with_key_all.sh "<manual_approval_token>"
```

## 6-5) Step7 비LLM 공격 매트릭스
```bash
cd /Users/jangjihyeon/201-goormgb-ai
python scripts/step7_attack_mode_matrix.py --frontend-url http://localhost:3000
```

실주행(Playwright 필요):
```bash
python scripts/step7_attack_mode_matrix.py --frontend-url http://localhost:3000 --execute
```

기본 매트릭스 전략:
- pass: `api_fast`, `humanish_pass`, `edge_pass`
- fail: `botlike_fail`, `timing_fail`, `token_tamper`
- 출력 요약: `logs/step7_attack_matrix_summary.json`

## 6-6) Step8 no-LLM 통합 체인
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step8_no_llm_all.sh
```

## 6-7) Step8 with-key 통합 체인
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
export TM_OFFLINE_LLM_API_KEY="<your_api_key>"
export TM_POLICY_APPLY_APPROVAL_TOKEN="<manual_approval_token>"
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step8_with_key.sh "<manual_approval_token>"
```

## 7) 앞으로의 작업 계획 (분리된 Step4)
- 실전형 **VQA solver(vision + trajectory)** 는 별도 단계(Step4)로 분리
- Step3의 목적은 인프라/정책/E2E 경로 안정화이며, solver 정교화는 범위 밖
- Step4 완료 조건(권장):
  - 공격 에이전트가 `catch_ball` 챌린지에 대해 pass/fail 모두 재현 가능
  - solver 성공률/지연/탐지율 지표를 audit log 기준으로 수치화
  - 우회 시나리오(DOM 주입/이벤트 위조) 회귀 테스트 세트 포함

## 정리
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose down
```
