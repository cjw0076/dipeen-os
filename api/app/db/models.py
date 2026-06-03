import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Text, Integer, Float, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    agents: Mapped[list["Agent"]] = relationship(back_populates="team")
    tasks: Mapped[list["Task"]] = relationship(back_populates="team")
    users: Mapped[list["User"]] = relationship(back_populates="team")
    projects: Mapped[list["Project"]] = relationship(back_populates="team")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("team_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(24), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planning")
    description: Mapped[str | None] = mapped_column(Text)
    repository_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    room_id: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    team: Mapped["Team"] = relationship(back_populates="projects")


class Node(Base):
    """프로젝트 그래프 노드 — Project 안의 PM/에이전트/사람 조직도.

    (Leekuejea ProjectAgent에서 흡수.) agents.metadata_json 기반 graph(ephemeral, team-scoped)와
    달리 *영속*되며 위치(pos)·계층(parent_id)을 프로젝트 단위로 보존한다 = project_agents 공백 충족.
    """
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100))   # 실제 Agent에 연결(있으면)
    node_class: Mapped[str] = mapped_column(String(20), default="agent")    # pm | agent
    node_type: Mapped[str] = mapped_column(String(20), default="ai")        # ai | human
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role_label: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(30), default="standby")
    accent_color: Mapped[str] = mapped_column(String(20), default="#38bdf8")
    stat_label: Mapped[str] = mapped_column(String(200), default="")
    pos_x: Mapped[float] = mapped_column(Float, default=0.0)
    pos_y: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProjectMember(Base):
    """프로젝트 레벨 멤버십/권한 — team 레벨(InviteCode/JWT)과 별개. (Leekuejea에서 흡수.)

    owner/editor/viewer 역할 + pending/active 상태. 프로젝트별 접근 제어의 1급 엔티티.
    """
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")     # owner | editor | viewer
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | active
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_emoji: Mapped[str] = mapped_column(String(10), default="👤")
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner | member
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    team: Mapped["Team | None"] = relationship(back_populates="users")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("team_id", "agent_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)  # "fe-agent"
    role: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="offline")
    current_task_id: Mapped[str | None] = mapped_column(String(100))
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # metadata_json 공식 스키마:
    # { skills: ["React","TypeScript"], mcps: ["filesystem","git"],
    #   competency: {"FE": 0-100}, model: "claude-sonnet-4-6",
    #   max_concurrent: 1, profile_hash: "md5..." }
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, default=dict)
    # F-3: 토큰 쿼터
    monthly_token_budget: Mapped[int | None] = mapped_column(Integer)  # null = 무제한
    tokens_used_this_month: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped["Team"] = relationship(back_populates="agents")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # "T-{uuid}"
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    complexity: Mapped[str | None] = mapped_column(String(20))
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    branch: Mapped[str | None] = mapped_column(String(200))
    pr_url: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict | None] = mapped_column(JSON)
    # 라우팅 (C-2 + F-3)
    required_role: Mapped[str | None] = mapped_column(String(20))        # "FE"|"BE"|"QA"|null
    required_skills: Mapped[list | None] = mapped_column(JSON, default=list)  # ["React","TypeScript"]
    required_persona: Mapped[str | None] = mapped_column(String(30))     # "coder"|"planner"|"researcher"|...
    # 서브태스크 + 의존성
    parent_task_id: Mapped[str | None] = mapped_column(String(100))  # 부모 T-{uuid}
    blocked_by: Mapped[str | None] = mapped_column(String(100))  # 이 태스크를 블록하는 T-{uuid}
    created_by_agent: Mapped[str | None] = mapped_column(String(50))  # 이 태스크를 생성한 agent_id
    max_duration_sec: Mapped[int | None] = mapped_column(Integer, default=600)  # 타임아웃 (초)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    team: Mapped["Team"] = relationship(back_populates="tasks")
    assigned_agent: Mapped["Agent | None"] = relationship()


class DecisionCard(Base):
    """Human-in-the-loop decision request.

    Agent Native Workspace에서 agent가 사람의 승인/선택/명확화를 기다리는 1급 큐.
    Provider/BYOK secret은 저장하지 않는다.
    """
    __tablename__ = "decision_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    decision_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(String(100), default="general", index=True)
    task_id: Mapped[str | None] = mapped_column(String(100), index=True)
    source_agent_id: Mapped[str | None] = mapped_column(String(100))
    decision_type: Mapped[str] = mapped_column(String(30), default="clarify")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON, default=list)
    recommended_option: Mapped[str | None] = mapped_column(String(300))
    risk: Mapped[str | None] = mapped_column(String(30))
    confidence: Mapped[float | None] = mapped_column(Float)
    cost_estimate: Mapped[str | None] = mapped_column(String(120))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    answered_by: Mapped[str | None] = mapped_column(String(100))
    delegated_to: Mapped[str | None] = mapped_column(String(100))
    audit_log: Mapped[list | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentMessage(Base):
    """에이전트 간 A2A 메시지 (C-5)"""
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))   # null = pm-loop/system
    to_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))     # null = broadcast
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    message_type: Mapped[str] = mapped_column(String(20), default="message")     # message|question|blocker
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(36))  # 답변 시 원본 id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChatMessage(Base):
    """채팅 메시지 영속성 (I-2)"""
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), default="user")  # user|pm|agent
    color: Mapped[str] = mapped_column(String(20), default="#FAFAFA")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # W-1: 구조화된 메타데이터 (progress, tool_use, started, completed, error)
    task_id: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    token_count: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
