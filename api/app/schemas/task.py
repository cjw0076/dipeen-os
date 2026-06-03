from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    subject: str
    prompt: str
    branch: str | None = None
    complexity: str | None = None
    required_role: str | None = None        # "FE"|"BE"|"QA"|null — C-2 라우팅용
    required_skills: list[str] = []         # ["React","TypeScript"] — C-2 스킬 매칭용
    required_persona: str | None = None     # "coder"|"planner"|"researcher"|... — F-3 페르소나 라우팅
    parent_task_id: str | None = None  # 서브태스크 생성 시
    blocked_by: str | None = None  # 의존 태스크 T-{uuid}
    created_by_agent: str | None = None  # agent가 생성한 경우


class TaskUpdate(BaseModel):
    status: str | None = None
    pr_url: str | None = None
    result: dict | None = None
    retry: bool = False  # S-1: error 태스크를 pending으로 재시도


class TaskOut(BaseModel):
    id: str
    task_id: str
    team_id: str
    subject: str
    prompt: str
    status: str
    complexity: str | None
    required_role: str | None
    required_skills: list | None
    required_persona: str | None
    assigned_agent_id: str | None
    branch: str | None
    pr_url: str | None
    result: dict | None
    parent_task_id: str | None
    blocked_by: str | None
    created_by_agent: str | None
    max_duration_sec: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
