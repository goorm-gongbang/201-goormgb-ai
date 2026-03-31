# Traffic-Master Defense MVP (D0) 방어 에이전트 워크플로우 가이드

본 문서는 `d0_mvp` 폴더 내 SSOT 명세(L0/L1/Annex 등)를 기반으로 방어 에이전트의 전체 워크플로우, 임계치(Threshold), 실패 처리 루프, 각 Act(Throttle, Challenge, Guard)의 동작 원리를 설명합니다.

---

## 1. 전사적 아키텍처 및 파이프라인 (Workflow)

방어 에이전트의 판단 논리 파이프라인은 단일 `/evaluate` 요청 내에서 4단계로 구성되어 동기적으로 실행됩니다.

1. **Guard (위험도 점수 산출)**
    - 클라이언트 트래픽의 텔레메트리(마우스 떨림, 마우스 이동 직선성 등)와 외부 봇 점수(Turnstile)를 결합합니다.
    - 단일 접속의 위험도(`s_t`)를 산출하고 지수이동평균(EWMA)을 통해 세션의 전체 위험도(`riskScore`)를 업데이트합니다.
    - 산출된 `riskScore`에 기반하여 위험 티어(Tier)를 결정합니다.
2. **Analyzer (증거 및 카운터수집)**
    - 결정적 룰을 바탕으로 증거와 카운터를 갱신합니다.
    - S3(미니게임) 단계의 `challengeFailCount`, 고가치 API 점유(Hold/Seat) 연속 실패 횟수 등의 상태값을 업데이트 및 평가합니다.
3. **Planner (액션 결정)**
    - Guard가 넘겨준 티어(Tier), 현재 플로우 상태(`flowState`), Analyzer의 증거 등을 바탕으로 수행할 방어 액션을 무상태(stateless)로 결정합니다.
    - **결정 가능한 Action**: `NONE`, `THROTTLE`, `REQUIRE_S3`, `BLOCK`
    - S3(검증 단계)를 아직 통과하지 않았는데 S4/S5로 진입하려 하면 상태를 불문하고 `REQUIRE_S3`(428)로 회귀시킵니다.
    - 이미 차단된 세션이면 즉시 `BLOCK`을 내립니다.
4. **Orchestrator (상태 커밋 및 집행 조합)**
    - Planner의 결정을 바탕으로 최종 응답 헤더(`x-defense-tier`, `x-defense-action` 등)를 포매팅합니다.
    - 유효하지 않은 단계 도약(ex: S1 -> S5)이 일어났는지 유효성을 검사합니다 (`INVALID_TRANSITION`, 409).
    - Envoy와 Adapter 등 실제 집행부에서 어떻게 처리해야 하는지 지시만 내리며, 런타임이 차단/지연을 직접 수행하진 않습니다.

---

## 2. Threshold (티어 및 임계치)

위험도(`riskScore`)는 0.0 에서 1.0 사이의 구간을 지니며, 다음의 임계치(Thresholds)를 거쳐 4단계의 Tier로 변환됩니다. 
- **T0 (0.0 ~ 0.2)**: 정상 사용자. 어떠한 지연/차단도 가해지지 않음 (`NONE`).
- **T1 (0.2 ~ 0.5)**: 의심 사용자(약). 짧은 지연(`THROTTLE`, 80ms)을 주입해 봇의 탐색 효율을 낮춤.
- **T2 (0.5 ~ 0.8)**: 의심 사용자(강). 강한 지연(`THROTTLE`, 250ms)을 주입해 매크로의 반복 탐색을 억제. 
- **T3 (0.8 ~ 1.0)**: 확인된 봇/공격자. 즉시 요청을 차단(`BLOCK`, 403)하고 해당 상태를 영구적으로(세션 만료 시까지) 기록.

> **Hysteresis(히스테리시스) 및 Probation**: 티어 변동 중 경계선에서 평가가 널뛰기하는 것을 방지하기 위해 마진(0.02)이 적용되어 있습니다. S3 VQA를 통과하면 일정시간 하향 완화 관찰을 겪는 `probation` 상태가 됩니다.

---

## 3. 각 세부 Act 동작 원리

### 3.1. Guard (산출 및 누적기)
- **Double-Hybrid Filter**: 외부 서비스 점수(Cloudflare Turnstile, 가중치 30%)와 내부 텔레메트리(프론트엔드 센서 데이터, 가중치 70%)를 하이브리드 결합합니다.
- **주요 텔레메트리 연산**: `tremorStdDev`(마우스 떨림), `linearityRatio`(직선성), `avgVelocity`(속도), `dwellTime`(머무른 시간), `pathRatio`(이동 경로 대비 최단거리 비율).
- **EWMA (지수이동평균) 누적**: 오탐지(False Positive) 방지를 위해 1회의 이벤트만으로 단번에 차단하지 않으며, 계속 누적되는 평균 공식을 사용합니다. $R_t = 0.7 * R_{t-1} + 0.3 * s_t$

### 3.2. Throttle (레이트 리밋이 아닌 Delay Injection)
- MVP의 Throttle은 요청을 버리는 Hard Rate Limit이 아닌 **Adapter Delay Injection*(Adapter 내부 sleep)* 방식**을 사용합니다.
- 주로 **탐색(Read) 계열 API**(예: `/api/seatmap`, `/api/availability`)에만 적용되어 악성 봇의 ROI를 붕괴시킵니다.
- 결제나 예매 확정 등 Write 계열 API(`/api/hold`, `/api/payment`)에는 적용되지 않아 실제 정상 유저라면 조금 느리더라도 티켓 구매를 확정 지을 수 있게 지원합니다.

### 3.3. Challenge (S3 고정형 VQA / 미니게임)
- MVP 로직에서 S3 단계는 반드시 거쳐야 하는 병목입니다. (무작위 "갑툭튀" 챌린지가 아님)
- **동작 방식**: 
  - 서버 시드 기반 정답 판정 방식(클라이언트는 검증 로직을 알 수 없음)의 야구공 캐치(`BASEBALL_CATCH`) 게임입니다.
  - S3 VQA를 풀지 않고 뒷 단계 진입 시 428 코드를 반환하여 풀이를 강제합니다.

---

## 4. 실패 처리 루프 (Failure Handling)

정상 유저가 실수로 챌린지에 실패했을 때 바로 차단(403)되지 않도록 부드러운 실패 처리 루프가 설정되어 있습니다.

### Challenge (VQA) 실패 시나리오 및 루프
1. **첫 번째 실패 (`ALLOW_RETRY`)**: 
   - 재시도 쿨다운 없이(0ms) 즉시 다시 시도할 수 있도록 허용합니다.
2. **두 번째 연속 실패 (`COOLDOWN_AND_RETRY`)**:
   - 악성 매크로의 무한 시도를 방지하기 위해 2.5초(2500ms)의 짧은 `Cooldown`을 부여하고 재시도를 허용합니다. (ROI 저하 유도)
3. **최대 시도 횟수(ex: 60초 내 2회) 초과 (`TEMPORARY_S3_HALT`)**:
   - 여전히 영구 차단(403)은 지양합니다. 다만, 무차별 대입을 무력화하기 위해 **429 (Too Many Requests)** 를 반환하고, 특정 시간(30초) 동안 S3 진행을 임시 보류(Halt)시킵니다.
4. **결함/장애 처리 (`FAIL_CLOSE_WITH_AUDIT`, 기본 정책)**:
   - VQA 서버 백엔드 타임아웃/연동 장애 시 기본 동작은 진행 차단(FAIL_CLOSE)입니다.
   - 응답은 `CHALLENGE_VERIFY_UNAVAILABLE(503)`으로 고정되며, 세션은 `S3`에 유지됩니다.
   - 시스템 장애는 사용자 실패로 누적하지 않으므로 `challengeFailCount`를 증가시키지 않습니다.
   - 운영 비상시에만 `TM_S3_VERIFY_UNAVAILABLE_MODE=fail_open` 오버라이드가 허용됩니다.

이와 같이 방어 에이전트는 단일 판단 오류에 유저가 배제되는 것을 방지하고(Guard EWMA 누적) 실패를 보완하는 부드러운 루틴(Challenge Fail Loop)과, 봇의 득실을 갉아먹는 페널티(Throttle)를 중심으로 설계되어 있습니다.
