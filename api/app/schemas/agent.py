from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentRegister(BaseModel):
    agent_id: str        # "fe-agent"
    role: str | None = None
    metadata: dict | None = None


class AgentHeartbeat(BaseModel):
    status: str          # idle/working/offline
    current_task_id: str | None = None


class AgentCapabilityUpdate(BaseModel):
    """C-1 + F-1: agent-client 시작 시 로컬 환경 스캔 결과 등록"""
    skills: list[str] = []           # ["React", "TypeScript", "CSS"]
    mcps: list[str] = []             # ["filesystem", "git", "github"]
    model: str | None = None         # "claude-sonnet-4-6"
    max_concurrent: int = 1
    llm_provider: str | None = None  # "anthropic"|"openai"|"google"|... — F-1
    personas: list[str] = []         # ["coder", "reviewer"] — F-1 페르소나 선언


class TaskArtifacts(BaseModel):
    """Result Distillation — 태스크 실행 결과의 최소 핵심 추출물.

    PM이 follow-up 태스크를 만들 때 전체 실행 로그 대신 이것만 참조.
    context window를 아끼면서도 연속성 있는 체인을 만드는 핵심 구조.
    """
    changed_files: list[str] = []     # git diff로 추출한 변경 파일 목록
    key_decisions: list[str] = []     # 에이전트가 내린 주요 기술 결정사항
    blockers: list[str] = []          # 완료 못한 항목 / 다음 에이전트가 알아야 할 것
    references: dict[str, str] = {}   # { "컴포넌트명": "파일경로:라인" } 형태 포인터
    # W1 솔기: RunReport 관련 필드 — 이전엔 정의가 없어 report 엔드포인트에서 *드롭*됐고
    # 그 결과 Gatekeeper의 PROMISE_FALSE/DETERMINISTIC_FAIL이 실제 보고에서 죽어 있었다.
    completion_promise: str | None = None   # 러너 자기보고(조작 금지) — HQ가 판정
    scope_diff: list[str] = []              # 실제 만진 경로 → scope_claims와 대조
    checks: dict[str, str] = {}             # {"pytest":"pass","ruff":"fail"} (R4, 기계 실행 결과)
    runner: str | None = None               # 어느 러너가 실행했나
    run_report: dict | None = None          # 첫째가는 RunReport dict (HQ가 재구성 없이 소비)
    pr_url: str | None = None               # K-5
    subtasks: list = []                     # K-8


class AgentReport(BaseModel):
    task_id: str
    status: str          # done/error/cancelled
    pr_url: str | None = None
    tests_passed: bool = False
    summary: str = ""
    usage: dict | None = None
    artifacts: TaskArtifacts | None = None  # Result Distillation


class AgentMessageCreate(BaseModel):
    """C-5: A2A 메시지 전송"""
    to_agent_id: str | None = None   # null = PM에게
    task_id: str | None = None
    message_type: Literal["message", "question", "blocker"] = "message"
    content: str
    reply_to: str | None = None      # 답변 시 원본 메시지 id


class AgentOut(BaseModel):
    id: str
    agent_id: str
    team_id: str
    role: str | None
    status: str
    current_task_id: str | None
    last_heartbeat: datetime | None
    metadata_json: dict | None
    monthly_token_budget: int | None = None
    tokens_used_this_month: int = 0

    model_config = {"from_attributes": True}


class RosterEntry(BaseModel):
    """C-3 + F-1: Roster API 응답의 단일 에이전트"""
    agent_id: str
    role: str | None
    status: str
    current_task_id: str | None
    available: bool
    skills: list[str]
    mcps: list[str]
    competency: dict[str, float]
    model: str
    max_concurrent: int
    last_heartbeat: str | None
    llm_provider: str          # "anthropic"|"openai"|"google"|...
    personas: list[str]        # ["coder", "reviewer"]
