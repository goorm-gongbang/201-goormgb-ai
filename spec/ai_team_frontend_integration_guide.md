# AI Team Internal: 프론트엔드 보안 연동 개발 명세 (3/19 Dev용)

본 문서는 **"대기열 진입 전 1차 봇 필터링"**을 위해 프론트엔드 팀이 구현해야 할 **Cloudflare Turnstile (Invisible Captcha)** 연동 명세서입니다.

현재 프론트엔드 코드(`platform/frontend`)에는 Turnstile 연동 로직이 부재하므로, 3월 19일 전체 하이브리드 아키텍처 연동을 위해 다음 기능들이 필수적으로 구현되어야 합니다.

---

## 1. 🎯구현 목표 및 워크플로우

유저가 콘서트 예매 페이지에서 **[예매하기]** 버튼을 클릭하는 순간, 백엔드 대기열(Queue) API를 호출하기 **직전**에 백그라운드에서 눈에 보이지 않는(Invisible) 캡챠를 통과시켜야 합니다.

1.  유저가 `[예매하기]` 클릭
2.  (프론트엔드) Cloudflare Turnstile 위젯 렌더링 (Invisible 모드)
3.  (Turnstile) 브라우저 환경 및 JS 챌린지 수행 ➡️ 성공 시 `cf-turnstile-response` 토큰 발급
4.  (프론트엔드) 발급받은 토큰을 포함하여 백엔드 대기열 API (예: `POST /api/booking/entry`) 호출
    *   *헤더 추가:* `x-turnstile-token: <발급받은_토큰>`

---

## 2. 📝 Frontend 구현 상세 가이드

### 2.1. 라이브러리 및 스크립트 추가
React 등 SPA 환경에 맞춰 가벼운 공식 Wrapper 라이브러리(`@marsidev/react-turnstile` 등)를 사용하거나 순수 스크립트로 연동합니다.

```html
<!-- index.html -->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
```

### 2.2. Invisible 컴포넌트 삽입
Turnstile 위젯은 화면에 UI를 전혀 그리지 않는 `invisible` 모드로 삽입되어야 합니다.

*   **Site Key:** 클라우드/보안 팀에서 발급받은 호스트네임 전용 퍼블릭 키
*   **실행 타이밍:** 예매하기 페이지 진입 시 컴포넌트를 마운트하여 백그라운드에서 미리 토큰을 준비시키면 체감 대기 시간이 0초에 수렴합니다.

```jsx
// React 예시
import { Turnstile } from '@marsidev/react-turnstile'

export function BookingButton() {
  const [token, setToken] = useState<string | null>(null);

  const handleBookingClick = () => {
    if (!token) return alert('보안 검증 중입니다. 잠시만 기다려주세요.');
    
    // 대기열 진입 API 호출 시 토큰 동봉
    api.post('/api/booking/entry', payload, {
      headers: { 'x-turnstile-token': token }
    });
  }

  return (
    <>
      <Turnstile
        siteKey="1x00000000000000000000AA" // 임시(Dummy) Site Key (개발계 적용용)
        options={{
          action: 'booking-entry',
          theme: 'auto',
          size: 'invisible', // 핵심: 유저에게 안 보이도록 설정
        }}
        onSuccess={(token) => setToken(token)}
      />
      
      <button onClick={handleBookingClick}>
        예매하기
      </button>
    </>
  )
}
```

---

## 3. 🚦 예외 처리 요구사항

*   **토큰 만료(Timeout):** 발급된 토큰은 일반적으로 5분 정도 지나면 정책적으로 만료됩니다. Turnstile 컴포넌트의 `onExpire` 콜백을 등록하여, 토큰이 만료되면 자동으로 백그라운드에서 재발급(`turnstile.reset()`) 받도록 처리해야 합니다.
*   **네트워크 오류:** Cloudflare 서버 자체가 오작동하거나 사용자의 강력한 브라우저 확장프로그램(Adblock 등)이 JS 실행을 막았을 때, **Fail-Open (무시하고 통과) 할지 Fail-Close (예매버튼 비활성화) 할지 정책 결정**이 필요합니다. (기본적으로는 예매하기가 불가능하도록 방어하는 Fail-Close 권장).
