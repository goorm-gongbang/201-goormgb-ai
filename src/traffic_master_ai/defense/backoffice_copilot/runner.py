"""
Live Runner for Backoffice Copilot

This script loads the .env file, initializes the OpenAI Adapters
using the credentials, and executes the Copilot workflow.
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
    # 사용자님이 가지고 계신 d0_mvp/.env 파일을 여기서 수동으로 로드!
    env_path = os.path.join(os.path.dirname(__file__), "..", "d0_mvp", ".env")
    load_dotenv(env_path)
except ImportError:
    pass

from traffic_master_ai.defense.backoffice_copilot import (
    BackofficeCopilotWorkflowDependencies,
    PostReviewRunInput,
    build_backoffice_copilot_workflow,
    build_openai_review_adapter,
    build_openai_summary_adapter,
)
from traffic_master_ai.defense.backoffice_copilot.storage import (
    PkConflictPolicy,
    PostgresPostReviewWriteRepository,
)
from traffic_master_ai.defense.backoffice_copilot.storage.connection import (
    build_postgres_engine,
)


def run_copilot_live(match_id: str, window_start_ms: int, window_end_ms: int) -> None:
    # 1. 사용자님이 알려주신 .env 키명 기준으로 추출
    api_key = os.getenv("TM_OFFLINE_LLM_API_KEY")
    model = os.getenv("TM_OFFLINE_LLM_MODEL", "gpt-4o-mini")
    endpoint = os.getenv("OPENAI_BASE_URL") or os.getenv("TM_OFFLINE_LLM_ENDPOINT", "https://api.openai.com/v1")

    if not api_key:
        print("ERROR: TM_OFFLINE_LLM_API_KEY is not set in environment or .env file.")
        sys.exit(1)

    print(f"[*] Initializing OpenAI Adapters")
    print(f"     - Model: {model}")
    print(f"     - Endpoint: {endpoint}")

    # 2. 파이프라인의 핵심 설정값 가져오기
    # DB 연결 정보 (sqlalchemy 패키지가 필요합니다)
    pg_url = os.getenv("TM_PG_URL")
    if not pg_url:
        print("ERROR: TM_PG_URL is not set. PostgreSQL connection is required for finished runner.")
        sys.exit(1)

    print(f"[*] Initializing PostgreSQL Engine...")
    engine = build_postgres_engine(pg_url)
    repository = PostgresPostReviewWriteRepository(
        engine=engine,
        conflict_policy=PkConflictPolicy.UPSERT,
    )

    # 3. 어댑터 팩토리 호출
    review_adapter = build_openai_review_adapter(
        api_key=api_key,
        model=model,
        endpoint=endpoint,
    )
    
    summary_adapter = build_openai_summary_adapter(
        api_key=api_key,
        model=model,
        endpoint=endpoint,
    )

    # 4. 워크플로우 의존성에 장착 (DB 레포지토리 연동 등)
    # 실제 원본 로그 파일의 위치 설정 (우선 테스트 fixture 경로로 고정, 운영시 변경 필요)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    log_file_path = os.getenv(
        "TM_AUDIT_JSONL_PATH", 
        os.path.join(base_dir, "tests", "defense", "fixtures", "backoffice_copilot", "single_candidate_t2.jsonl")
    )

    dependencies = BackofficeCopilotWorkflowDependencies(
        audit_events_jsonl_path=log_file_path,
        repository=repository,
        conflict_policy=PkConflictPolicy.UPSERT,
        llm_review_adapter=review_adapter,
        summary_adapter=summary_adapter,
    )

    # 5. 워크플로우 조립 및 실행
    workflow_app = build_backoffice_copilot_workflow(dependencies)
    
    run_input = PostReviewRunInput(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        limit=1000,
        use_raw_audit_fallback=True,
    )

    print(f"[*] Raw logs target path: {log_file_path}")
    print(f"\n[*] Executing workflow for match_id: {match_id} (Window: {window_start_ms} ~ {window_end_ms})")
    
    # 워크플로우 가동! (에러 발생 시 내부에 저장되거나 Fallback 시스템 가동)
    result = workflow_app.invoke(run_input)
    print(f"[*] Workflow finished with final status: {result.final_status}")
    if result.validation_outcome:
        print(f"[*] Validation outcome status: {result.validation_outcome.final_status}")


if __name__ == "__main__":
    import time
    now_ms = int(time.time() * 1000)
    # 직전 10분의 데이터를 확인하는 통합 파이프라인 시작
    run_copilot_live("live-test-002", now_ms - (10 * 60 * 1000), now_ms)
