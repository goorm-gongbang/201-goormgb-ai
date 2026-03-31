# Step4 Recommended Execution Order

> Note:
> `src/traffic_master_ai/defense/d0_poc/...` 경로명은 레거시 이름입니다.
> 현재 작업은 **PoC-0 재현이 아니라 MVP 통합 트랙**입니다.
> ST4는 MVP 통합을 위한 중간 고정 단계(로컬 파일럿 + 품질게이트)로 운영합니다.

1. **ST4-1**: Attack Agent Challenge Bridge (deterministic pass/fail)
2. **ST4-2**: Catch-Ball Solver v1 (trajectory + timing)
3. **ST4-3**: Metrics & Quality Gate
4. **ST4-4**: Bypass Regression Suite

## API Key / LLM Notice
- Step4 baseline does **not** require external LLM API keys.
- If any step introduces external LLM/VLM, stop and request key provisioning first.
