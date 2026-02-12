# 🚀 Local Testbed Startup Guide

본 가이드는 `feat/mvp-testbed` 브랜치에서 행동 데이터를 수집하기 위해 서버를 기동하는 방법을 설명합니다.

## 1. Backend (Spring Boot) 서버 기동
백엔드는 수집된 행동 피처(M-Prim)를 수신하고 로깅하는 역할을 합니다.

### **방법 A: IntelliJ IDEA 활용 (추천)**
- 사용자님의 기술 스택에 있는 **IntelliJ**로 `platform/backend` 폴더를 엽니다.
- `build.gradle` 파일을 우클릭하여 **"Import Gradle Project"**를 선택합니다.
- 오른쪽 Gradle 탭에서 `Tasks > application > bootRun`을 실행하거나, `DefenderApplication.java`를 직접 실행합니다.

### **방법 B: 터미널 활용**
- Gradle이 설치되어 있지 않다면 먼저 설치가 필요합니다: `brew install gradle`
- 설치 후: `gradle bootRun`

## 2. Frontend (Next.js) 서버 기동
사용자가 직접 마우스 움직임을 '연기'할 UI 환경입니다.

```bash
cd platform/frontend
npm run dev
```
- **포트**: `http://localhost:3000`
- **접속**: 브라우저에서 `http://localhost:3000`으로 이동합니다.

## 3. 데이터 수집 방법 (Nogada Workflow)
1. 브라우저에서 **좌석 선택 페이지**에 접속합니다.
2. 마우스를 **인간답게** 움직여서 원하는 좌석 위로 이동합니다.
3. 좌석을 **클릭**합니다.
4. 클릭 직후, 하단 **"Last Interaction"** 패널에 실시간으로 추출된 `Linearity`, `Tremor`, `Dwell Time` 등이 표시되는지 확인합니다.
5. **백엔드 터미널 로그**를 확인하여 `Received Telemetry: ...` 메시지가 찍히는지 확인합니다.

---

> [!TIP]
> **다양한 페르소나를 연기해 보세요!**
> - 아주 직선적이고 빠른 움직임 (Aggressive)
> - 머뭇거리며 곡선을 그리거나 떨림이 있는 움직임 (Stealth/Natural)
> 이렇게 쌓인 로그가 나중에 AI의 '행동 뱅크'가 됩니다.
