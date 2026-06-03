"""NAT contracts (§21 step 1) — Dipeen Core가 아는 *유일한* 타입.

원칙(Isolation): Claude/Codex/OMO/Hermes의 내부 개념(prompt/workflow/goal/reflection)은 절대 여기 안 들어온다.
Core는 Identity/Task/State/Event/Artifact/MemoryCandidate/Permission/Run만 안다.
순수 스키마(IO·LLM 없음). 출처: docs/nat-architecture-v1.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import BaseModel, Field
import uuid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ════════════════════ State (claim ≠ task ≠ agent — §2.3, 절대 안 섞음) ════════════════════
TaskState = Literal[
    "CREATED", "READY", "ASSIGNED", "RUNNING", "AWAITING_PERMISSION",
    "VERIFYING", "NEEDS_RETRY", "BLOCKED", "REJECTED", "DONE", "FAILED", "CANCELLED",
]
AgentState = Literal["IDLE", "STARTING", "RUNNING", "WAITING", "STOPPING", "FAILED", "UNHEALTHY"]
ClaimedState = Literal["working", "done", "failed", "blocked", "needs_input"]
RunState = Literal["CREATED", "RUNNING", "CLOSED"]

FailureType = Literal[
    "test_failed", "artifact_missing", "permission_denied", "timeout",
    "agent_crash", "invalid_output", "acceptance_not_met", "merge_conflict", "policy_violation",
]


# ════════════════════ Identity NAT (§2.1) ════════════════════
class AgentBinding(BaseModel):
    adapter: str                                  # claude | codex | omo | hermes
    runtime: Optional[str] = None                 # claude-code | opencode | …
    session_id: Optional[str] = None


class AgentIdentity(BaseModel):
    """agent://team/{role} ↔ 실에이전트 binding. Conductor는 identity만 알고 실에이전트는 모른다."""
    identity_id: str                              # "agent://team/frontend"
    role: str                                     # frontend | backend | research | qa | pm
    binding: AgentBinding
    capabilities: list[str] = Field(default_factory=list)   # workspace.read/write, shell.run, git.diff …
    trust_level: Literal["sandboxed", "trusted", "privileged"] = "sandboxed"


# ════════════════════ Task NAT (§2.2) — 조직 작업 계약 ════════════════════
class TaskScope(BaseModel):
    repo: Optional[str] = None
    paths: list[str] = Field(default_factory=list)


class _ArtifactRequired(BaseModel):
    type: Literal["artifact_required"] = "artifact_required"
    artifact_type: str                            # "code_patch" …


class _CommandRequired(BaseModel):
    type: Literal["command_required"] = "command_required"
    command: str                                  # "npm test"
    must_pass: bool = True


class _FileRequired(BaseModel):
    type: Literal["file_required"] = "file_required"
    path: str                                     # "src/app/login/page.tsx"


# 검증가능 완료 기준(구조화, 'type'으로 판별). Verifier가 증거로 기계검증.
AcceptanceCriterion = Annotated[
    Union[_ArtifactRequired, _CommandRequired, _FileRequired],
    Field(discriminator="type"),
]


class PermissionPolicy(BaseModel):
    allow_workspace_write: bool = True
    require_approval_for_git_push: bool = True
    require_approval_for_network: bool = True


class MemoryPolicy(BaseModel):
    read_project_memory: bool = True
    write_memory_candidates: bool = True
    auto_promote_memory: bool = False             # 자동 승격 금지(candidate→review→promote)


class TaskEnvelope(BaseModel):
    """Task=prompt도 workflow도 goal도 아니다 — 조직이 수행할 작업 계약. agent별로 NAT가 번역."""
    task_id: str = Field(default_factory=lambda: _uid("T"))
    title: str
    intent: str
    scope: TaskScope = Field(default_factory=TaskScope)
    constraints: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    priority: Literal["low", "normal", "high"] = "normal"
    dependencies: list[str] = Field(default_factory=list)
    permission_policy: PermissionPolicy = Field(default_factory=PermissionPolicy)
    memory_policy: MemoryPolicy = Field(default_factory=MemoryPolicy)
    state: TaskState = "CREATED"


# ════════════════════ Run (retry = 새 Run, §6) ════════════════════
class Run(BaseModel):
    run_id: str = Field(default_factory=lambda: _uid("R"))
    task_id: str
    identity_id: str
    attempt: int = 1
    state: RunState = "CREATED"
    failure_type: Optional[FailureType] = None
    created_at: datetime = Field(default_factory=_now)


# ════════════════════ Event NAT (§2.4) — append-only ════════════════════
EventType = Literal[
    "task.created", "task.assigned", "task.started", "task.blocked", "task.retry_requested", "task.completed",
    "agent.started", "agent.working", "agent.waiting", "agent.failed", "agent.stopped",
    "artifact.produced", "artifact.verified", "artifact.rejected",
    "state.claimed", "state.reconciled",
    "permission.requested", "permission.approved", "permission.rejected", "permission.executed",
    "discussion.message", "decision.proposed", "decision.voted", "decision.accepted",
    "memory.candidate_created", "memory.promoted", "memory.rejected",
    "provider.probed", "provider.subtask", "long_task.checkpoint",
]


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: _uid("E"))
    event_type: EventType
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    producer: str = ""                            # agent://… 또는 dipeen://…
    message: str = ""
    raw_event_ref: Optional[str] = None           # raw://runs/R-…/events/N (원문 포인터, 신뢰 안 함)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


# ════════════════════ State NAT — StateClaim(주장, 신뢰 X) ════════════════════
class StateClaim(BaseModel):
    claim_id: str = Field(default_factory=lambda: _uid("SC"))
    task_id: str
    run_id: str
    producer: str                                 # agent://team/frontend
    claimed_state: ClaimedState                   # agent가 *주장*. TaskState는 Reconciler가 결정.
    message: str = ""
    created_at: datetime = Field(default_factory=_now)


# ════════════════════ Artifact NAT (§2.5, 핵심) ════════════════════
ArtifactType = Literal[
    "code_patch", "file_change_set", "command_receipt", "test_report", "review_result",
    "plan", "decision_proposal", "memory_candidate", "skill_candidate",
    "pr_reference", "issue_reference", "document", "metric", "context_evidence",
]
ArtifactStatus = Literal["produced", "verified", "rejected"]


class ArtifactProducer(BaseModel):
    identity: str                                 # agent://team/frontend
    adapter: Optional[str] = None                 # claude
    provider: Optional[str] = None                # anthropic


class ArtifactLocation(BaseModel):
    uri: str
    sha256: Optional[str] = None
    media_type: Optional[str] = None


class Evidence(BaseModel):
    kind: str                                     # git_diff_exists | test_passed | manual_approval …
    passed: bool
    message: Optional[str] = None


class ArtifactLink(BaseModel):
    relation: str                                 # implements | derived_from | …
    target_type: str                              # task | run | artifact
    target_id: str


class Artifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: _uid("A"))
    type: ArtifactType
    status: ArtifactStatus = "produced"
    task_id: str
    run_id: Optional[str] = None
    producer: ArtifactProducer
    title: str = ""
    summary: str = ""
    locations: list[ArtifactLocation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    links: list[ArtifactLink] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


# ════════════════════ Permission NAT (§2.7) — agent는 요청만, Dipeen이 실행 ════════════════════
PermissionAction = Literal[
    "workspace.read", "workspace.write", "shell.run", "network.request", "package.install",
    "git.diff", "git.commit", "git.push", "github.issue.create", "github.pr.create",
    "secret.read", "deployment.run",
]


# agent는 요청만 / PolicyEngine이 분류 / 로컬 Worker가 승인 후 실행 (Core는 실행 안 함, §M7 D-001)
PolicyDecision = Literal["deny", "require_human_approval", "auto_allow", "manual_handoff"]


class PermissionRequest(BaseModel):
    permission_request_id: str = Field(default_factory=lambda: _uid("P"))
    task_id: str
    run_id: str
    requester: str                                # agent://team/frontend
    action: PermissionAction
    target: Optional[str] = None
    reason: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    requires_human_approval: bool = True
    state: Literal["requested", "approved", "rejected", "executed"] = "requested"
    policy_decision: Optional[PolicyDecision] = None   # PolicyEngine 분류 결과
    decided_by: Optional[str] = None                   # user://… (사람 승인자)
    worker_id: Optional[str] = None                    # 실행할 worker
    workspace_root: str = ""                            # 실행 컨텍스트(로컬 경로)
    payload: dict[str, Any] = Field(default_factory=dict)   # executor 파라미터(branch/base/title…)


# ════════════════════ Memory NAT (§2.6) — candidate만(직접 쓰기 금지) ════════════════════
MemoryType = Literal["working", "task", "project", "project_decision", "organization", "personal"]


class MemoryCandidate(BaseModel):
    memory_candidate_id: str = Field(default_factory=lambda: _uid("M-CAND"))
    source_artifact_id: Optional[str] = None
    memory_type: MemoryType = "project"
    proposed_content: str = ""
    confidence: float = 0.5
    promotion_policy: Literal["requires_review", "auto"] = "requires_review"


class SkillCandidate(BaseModel):
    """경험에서 만든 skill 후보(Hermes 등). memory와 동일 — 자동승격 금지(candidate→review→promote)."""
    skill_candidate_id: str = Field(default_factory=lambda: _uid("S-CAND"))
    source_artifact_id: Optional[str] = None
    name: str = ""
    description: str = ""
    confidence: float = 0.5
    promotion_policy: Literal["requires_review", "auto"] = "requires_review"


# ════════════════════ Adapter ↔ NAT 경계 타입 (§10) ════════════════════
class AgentInvocation(BaseModel):
    """Outbound NAT 산출 → Adapter.run 입력. *중립* 실행요청(어느 agent든 동일 형태).
    prompt=렌더된 지시문(provider별 렌더는 Outbound 책임) — 어댑터는 자기 CLI로 실행만.
    env: 실행환경 override. 값이 ""면 그 키 제거(구독 크레딧0: ANTHROPIC_API_KEY="").
    """
    run_id: str
    identity_id: str
    prompt: str
    workspace_root: str
    timeout_sec: Optional[int] = None
    env: dict[str, str] = Field(default_factory=dict)
    session_id: Optional[str] = None


class RawAgentOutput(BaseModel):
    """Adapter.run의 반환 = **RunReport**(worker 실행 증거). NAT(Inbound)가 이걸 normalized로 번역.
    어댑터는 이 이상(artifact/state/memory) 만들지 않는다(Isolation).

    추적성(replay 입력): runner/command/cwd는 adapter가, worker_id는 *실행 노드*(worker_execute)가
    채운다 — "누가(runner)·무엇을(command)·어디서(cwd)·어느 노드에서(worker_id)" 돌았는지 자기기술.
    """
    run_id: str
    identity_id: str
    runner: Optional[str] = None                       # 실행 adapter(claude|codex|omo|hermes|fake)
    command: list[str] = Field(default_factory=list)   # 실제 argv(번역 아님 — 그대로, replay용)
    cwd: Optional[str] = None                          # 실행 디렉토리(subprocess cwd)
    worker_id: Optional[str] = None                    # 실행 worker 노드(adapter는 모름 — worker_execute가 stamp)
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    changed_files: list[str] = Field(default_factory=list)
    raw_events: list[dict[str, Any]] = Field(default_factory=list)
    workspace_root: Optional[str] = None
    session_id: Optional[str] = None


class NormalizedAgentResult(BaseModel):
    """Inbound NAT 산출 — raw → Dipeen 공통 계약 5종."""
    events: list[Event] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    state_claims: list[StateClaim] = Field(default_factory=list)
    permission_requests: list[PermissionRequest] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    skill_candidates: list[SkillCandidate] = Field(default_factory=list)


# ════════════════════ Core↔Worker 트랜스포트 (§M6) — pull command queue ════════════════════
CommandType = Literal["run.start", "run.stop", "permission.execute", "provider.probe"]
CommandState = Literal["queued", "leased", "running", "completed", "failed", "expired"]


class Command(BaseModel):
    """Core가 Worker에게 내리는 실행 지시. Worker가 *pull*(poll)로 가져가 lease 후 실행한다.
    Core는 worker에 직접 접속하지 않는다(worker가 방화벽 뒤여도 OK). complete ≠ task done."""
    command_id: str = Field(default_factory=lambda: _uid("CMD"))
    command_type: CommandType = "run.start"
    task_id: Optional[str] = None                  # provider.probe는 task-less(run.start/permission은 채움)
    run_id: Optional[str] = None
    provider: str                                  # claude | codex (어느 adapter로 실행)
    task: Optional[TaskEnvelope] = None            # 실행 페이로드(remote worker가 store 없이 실행)
    workspace_ref: Optional[str] = None            # workspace://ezmap-web — worker가 자기 local_path로 resolve
    repo: Optional[str] = None                     # repo.ezmap-web (라우팅/표시)
    workspace_root: str = ""                       # legacy 절대경로 fallback(HQ는 안 싣는 게 원칙)
    required_capabilities: list[str] = Field(default_factory=list)   # provider.claude, workspace.write…
    state: CommandState = "queued"
    lease_owner: Optional[str] = None              # 점유 worker_id
    lease_expires_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None
    permission_id: Optional[str] = None            # permission.execute일 때 PermissionRequest 링크
    payload: dict[str, Any] = Field(default_factory=dict)   # permission.execute: {action,target,branch…}
    created_at: datetime = Field(default_factory=_now)


class WorkerWorkspace(BaseModel):
    """worker가 보유한 작업 공간. **local_path는 worker-local** — HQ는 디버그용으로만 보관하고
    dispatch가 이 경로에 의존하지 않는다. worker가 workspace_ref → local_path를 resolve한다."""
    workspace_ref: str                             # workspace://ezmap-web (HQ가 아는 추상 참조)
    repo: Optional[str] = None                     # repo.ezmap-web
    repo_url: Optional[str] = None                 # github://… (선택)
    local_path: str = ""                           # worker-local 절대경로 — HQ는 의존 안 함
    capabilities: list[str] = Field(default_factory=list)   # repo.ezmap-web, workspace.write, test.npm…


class WorkerInfo(BaseModel):
    """Worker(현장 노드) 등록 정보. capability 기반 dispatch + heartbeat 생존."""
    worker_id: str
    capabilities: list[str] = Field(default_factory=list)   # provider.claude, provider.codex, workspace.write…
    workspaces: list[WorkerWorkspace] = Field(default_factory=list)   # 보유 작업공간(workspace_ref→local)
    last_heartbeat: datetime = Field(default_factory=_now)
    state: Literal["online", "offline"] = "online"


# ════════════════════ Room / Message (§M8 agentic Slack) ════════════════════
# room = 조직 객체에 붙는 typed 채널. message = 채팅 아닌 typed event. **message ≠ 실행**:
# message.created → command.proposed → (confirm) → command.queued (대화와 실행 분리).
RoomType = Literal["general", "goal", "task", "run", "permission", "memory", "discussion"]
MessageType = Literal["discussion.message", "decision.proposal", "command.proposal", "system"]
SenderType = Literal["human", "agent", "system"]
ProposalState = Literal["proposed", "confirmed", "rejected"]


class SenderRef(BaseModel):
    type: SenderType
    id: str                                       # user://cjw | agent://team/frontend | dipeen://core


class MessageLink(BaseModel):
    target_type: str                              # task | run | artifact | decision
    target_id: str


class Room(BaseModel):
    room_id: str
    room_type: RoomType = "general"
    ref_id: Optional[str] = None                  # 붙은 조직 객체(goal/task/run/permission/memory) id
    title: str = ""
    created_at: datetime = Field(default_factory=_now)


class Message(BaseModel):
    message_id: str = Field(default_factory=lambda: _uid("MSG"))
    room_id: str
    sender: SenderRef
    message_type: MessageType = "discussion.message"
    body: str = ""
    links: list[MessageLink] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class AssignmentSpec(BaseModel):
    """회의에서 정해진 배정 — 작업을 특정 role/user/repo/worker로 라우팅한다.

    `assignment_to_capabilities`가 이를 Command.required_capabilities로 변환하고, CommandQueue.poll이
    `required ⊆ worker.capabilities`로 lease하므로 *맞는 worker만* 작업을 가져간다(HQ가 push하지 않음).
    필드를 많이 채울수록 라우팅이 좁아진다(role pool → 특정 사람의 특정 머신). 비우면 하위호환 풀 라우팅.
    """
    role: Optional[str] = None                    # frontend | backend | qa | integrator | memory …
    user: Optional[str] = None                    # minjun (사람)
    repo: Optional[str] = None                    # ezmap-web (repo slug)
    workspace_ref: Optional[str] = None           # workspace://ezmap-web (command에 실려 worker가 resolve)
    preferred_worker: Optional[str] = None        # worker.minjun-mac (특정 머신)
    provider: Optional[str] = None                # provider 오버라이드(없으면 proposal.provider)


class CommandProposal(BaseModel):
    """message → command proposal → (confirm) → queue. **채팅이 바로 실행되지 않게** 하는 안전 경계.
    제안만으론 아무 실행도 없다 — 사람/정책이 confirm해야 Command가 enqueue된다."""
    proposal_id: str = Field(default_factory=lambda: _uid("PROP"))
    room_id: str
    message_id: Optional[str] = None
    proposed_by: str                              # agent://team/pm | user://cjw
    intent: str
    provider: str                                 # claude | codex
    workspace_root: str = ""
    assignment: Optional[AssignmentSpec] = None   # 배정(역할/사람/repo/worker) → required_capabilities
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    state: ProposalState = "proposed"
    decided_by: Optional[str] = None              # confirm/reject한 주체
    task_id: Optional[str] = None                 # confirm 시 생성된 task
    command_id: Optional[str] = None              # confirm 시 enqueue된 command
    created_at: datetime = Field(default_factory=_now)


# ════════════════════ Meeting Closure (4단계) — 회의 정리, 승인 전엔 작업 아님 ════════════════════
class ActionCandidate(BaseModel):
    """작업 *후보* — 바로 task가 아니다. 승인되면 CommandProposal(배정 포함)로 승격된다."""
    candidate_id: str = Field(default_factory=lambda: _uid("AC"))
    source_message_ids: list[str] = Field(default_factory=list)
    title: str = ""
    intent: str
    scope: dict[str, Any] = Field(default_factory=dict)   # {repo, paths, workspace_ref}
    suggested_role: Optional[str] = None                  # frontend/backend/qa…(UI에서 사람이 확정)
    suggested_provider: str = "claude"
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    state: str = "candidate"


class DecisionCandidate(BaseModel):
    """결정 *후보* — 승인되면 DecisionRecord(event)로 남는다(코드 변경 아님)."""
    candidate_id: str = Field(default_factory=lambda: _uid("DC"))
    source_message_ids: list[str] = Field(default_factory=list)
    statement: str
    state: str = "candidate"


class MeetingClosurePacket(BaseModel):
    """회의 종료 시 정리물 — decision/task/permission/memory/question으로 분류. **후보만**, 실행 0."""
    meeting_id: str = Field(default_factory=lambda: _uid("MEET"))
    room_id: str
    decisions: list[DecisionCandidate] = Field(default_factory=list)
    task_candidates: list[ActionCandidate] = Field(default_factory=list)
    permission_candidates: list[str] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
