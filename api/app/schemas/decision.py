from datetime import datetime

from pydantic import BaseModel, Field


class DecisionCreate(BaseModel):
    room_id: str = "general"
    task_id: str | None = None
    source_agent_id: str | None = None
    decision_type: str = "clarify"  # approve | choose | unblock | clarify | escalate
    question: str
    context: str | None = None
    options: list[str] = Field(default_factory=list)
    recommended_option: str | None = None
    risk: str | None = None
    confidence: float | None = None
    cost_estimate: str | None = None
    deadline: datetime | None = None


class DecisionAnswer(BaseModel):
    answer: str
    note: str | None = None
    answered_by: str = "human"


class DecisionDelegate(BaseModel):
    delegate_to: str
    note: str | None = None


class DecisionOut(BaseModel):
    id: str
    team_id: str
    decision_id: str
    room_id: str
    task_id: str | None
    source_agent_id: str | None
    decision_type: str
    question: str
    context: str | None
    options: list | None
    recommended_option: str | None
    risk: str | None
    confidence: float | None
    cost_estimate: str | None
    deadline: datetime | None
    status: str
    answer: str | None
    note: str | None
    answered_by: str | None
    delegated_to: str | None
    audit_log: list | None
    created_at: datetime
    updated_at: datetime
    answered_at: datetime | None
    server_receives_provider_keys: bool = False

    model_config = {"from_attributes": True}
