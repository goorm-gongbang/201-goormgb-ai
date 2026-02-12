# 🎨 Traffic-Master Frontend

Next.js 16 (Turbopack) 기반의 티켓 예매 SPA입니다.

## 실행

```bash
npm install   # 최초 1회
npm run dev   # http://localhost:3000
```

## 프로젝트 구조

```
src/
├── app/              # Next.js App Router 페이지
│   ├── page.tsx      # 홈 (공연 목록)
│   ├── queue/        # 대기열 화면
│   └── seats/        # 좌석 선택 화면
├── components/
│   ├── queue/        # 대기열 UI
│   ├── seats/        # 좌석 지도, 추천 패널
│   ├── security/     # 보안 퀴즈 모달 (SecurityLayer)
│   └── payment/      # 결제 UI
├── stores/           # Zustand 상태 관리
│   ├── useSeatStore  # 좌석 선택 상태
│   └── useSecurityStore  # 보안 퀴즈 상태
├── services/
│   ├── api.ts        # Axios 인스턴스 + 세션 관리
│   └── apiClient.ts  # Fetch 기반 클라이언트 + 글로벌 에러 핸들링
└── hooks/            # 커스텀 훅 (useQueuePolling 등)
```

## 주요 기술 스택

- **Next.js 16** (App Router, Turbopack)
- **React 19**
- **Zustand** (상태 관리)
- **TypeScript**
