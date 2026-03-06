# Delivery Bundle (2026-03-04)

이 폴더는 타 팀 전달용 패키지입니다.

- `CI/`: Cloud/Infra 연동용 API, Docker, 저장전략, 체크리스트
- `FE/`: FE 연동 계약/가이드 + selector 계약
- `BE/`: BE 연동 계약/SSOT/API 가이드

원본 문서는 `spec/` 및 `src/` 경로에 있습니다.
번들 전체 가변값 정책은 `CONFIGURABILITY_POLICY.md`를 기준으로 합니다.
문서 충돌 시 `DEFENSE_CONSISTENCY_LOCK_V1.md`를 우선 적용합니다.

VQA 정책 고정(v1):
- Queue 통과 직후 1회 고정 challenge
- 세션 진행 중 tier 상승만으로 추가 challenge 금지

## Contract Governance (중요)

이 번들의 숫자/포트/임계값은 아래 규칙으로 해석합니다.

- 고정 계약(Fixed):
  - API 필드명/타입
  - 이벤트명
  - 헤더 키(`x-defense-action` 등)
  - ReasonCode enum
  - 상태/전이 명칭(S0~SX, T0~T3)
- 운영 가변(Tunable):
  - 임계값(threshold), TTL, delay, budget
  - 포트/호스트/경로 prefix
  - 챌린지 타입/난이도/최대시도

운영 가변값은 기본적으로 ENV 또는 정책 스냅샷으로 관리하며, 문서 내 숫자는 baseline 예시값입니다.
