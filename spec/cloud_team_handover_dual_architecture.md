# Traffic Master - Dual Defense & Dual Blocking 아키텍처 명세서 (3/19 Dev 배포 기준)

본 문서는 클라우드 팀 및 백엔드 팀 회의록(3월 19일 Dev 배포 논의)을 바탕으로, **방어막의 역할(Cloudflare vs In-house VQA)**과 **차단 매커니즘(Istio 프록시 vs BE AuthGuard)**을 명확히 정의합니다.

---

## 1. 🛡️ Dual Defense (투트랙 캡챠 방어망)

사용자의 예매 여정 중 발생하는 마찰(Friction)을 최소화하면서도 봇 차단율을 극대화하기 위해, 캡챠 방어망을 **가시성(Visibility)** 강도에 따라 두 단계로 분리 운영합니다.

### Layer 1: Cloudflare Turnstile (Invisible) - 대기열 진입 전
*   **발동 위치:** 프론트엔드에서 '예매하기(Booking)' 버튼을 누르는 순간. 대기열(Queue) 진입 직전 수행.
*   **특징:** 유저에게 문제를 풀게 하지 않는 **비가시성(Invisible) 캡챠**. 브라우저 환경 및 간단한 JS 연산 증명을 백그라운드에서 조용히 수행합니다.
*   **운영 주체:** 프론트엔드 - Cloudflare 서버 간 직접 연동 후, 획득한 토큰을 BE/Istio로 전달.
*   **목적:** 대량의 단순 하급 봇(Scripted Bots)을 대기열 진입 전에 1차적으로 털어냅니다.

### Layer 2: In-house VQA (Interactive) - 예매 여정 중 (AI 개입)
*   **발동 위치:** 대기열 통과 후 실제 좌석 선택, 결제 등 주요 크리티컬 API 경로.
*   **특징:** Cloudflare를 통과한 고도화된 봇(Headless Browser 등)을 잡기 위한 **가시성(Interactive) 자체 구축 캡챠 (공 잡기 등)**.
*   **동작 방식:** Istio를 거쳐 AI Defense 서버가 유저의 마우스 궤적(Telemetry)을 분석하여 "봇 의심(T2)" 판정을 내릴 때만 선택적(Targeted)으로 발동합니다.
*   **목적:** Turnstile을 우회하는 정교한 봇의 행동 맥락을 끊고, 휴먼 증명을 강제합니다.

> 💡 **요약:** 
> 무조건 띄우는 1차 방어막은 조용한 **Cloudflare Turnstile**, 
> 이상 행동감지 시에만 띄우는 2차 강력 방어막은 우리의 **자체 VQA 시스템**입니다.

---

## 2. 🧱 Dual Blocking (이중 차단 아키텍처)

클라우드(Istio)와 백엔드(Spring)의 권한 검증(Auth) 계층은 중복이 아닌 완벽한 상호 보완재입니다. AI Defense는 악성 유저 발견 시 이 두 계층 모두에 제재를 가합니다.

### 2.1. 역할 분담: Istio ext_authz vs Backend AuthGuard

| 구분 | Istio (Envoy ext_authz) + AI Defense | Backend (Spring AuthGuard) |
| :--- | :--- | :--- |
| **목적** | **L7 워크로드 방어 (Mitigation)** <br> 악성 봇 트래픽 조기 차단 | **비즈니스 인가 (Authorization)** <br> 유저의 리소스 접근 권한 확인 |
| **기준** | 행위 기반 (Telemetry 궤적, API 반복 패턴 등) | 신분 기반 (JWT 서명 유효성, Role 등) |
| **장점** | JVM 스레드를 점유하기 전 프록시 단에서 차단하여 서버 부하 원천 차단 | 데이터베이스 레벨의 비즈니스 규칙과 완벽한 정합성 보장 |

### 2.2. 이중 제재(Dual-Blocking) 워크플로우

1.  **악성 감지:** 유저(해커)가 위변조된 JWT 릴레이 공격 등을 시도하거나 봇 궤적으로 결제 API 치팅 시도.
2.  **AI 판정:** AI Defense 서버가 `POST /evaluate` 요청을 받고 **차단(BLOCK)** 확정 판정.
3.  **제재 1 (Network Layer):** AI 서버가 Envoy에게 `action: BLOCK (403)` 응답을 주어 해당 트래픽의 백엔드 진입을 즉시 방어.
4.  **제재 2 (Application Layer):** AI 서버가 차단 응답과 **동시에 비동기로** 백엔드의 `POST /api/v1/internal/sanctions` (제재 API)를 호출.
    *   **Payload:** `{"target": "<JWT_User_Id>", "action": "REVOKE_TOKEN"}`
    *   백엔드는 해당 유저의 JWT Refresh Token 무효화 강제 로그아웃 처리, 및 예매 중이던 좌석 락(Lock) 강제 릴리즈 처리.

> 💡 **요약:** 
> Istio는 현재 들어오는 **해당 트래픽 파편을 튕겨내는 방패**이고, 백엔드 AuthGuard 토큰 정지는 **해당 유저의 무기(인증) 자체를 부러뜨리는 행위**입니다. 위변조된 JWT 토큰으로 뚫고 들어오려는 시도조차 원천 차단하기 위해서는 이중 차단(Dual-Blocking)이 필수적입니다.
