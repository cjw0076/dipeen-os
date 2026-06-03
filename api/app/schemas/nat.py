"""NAT — Agent Translation Layer 공통 계약 (Dipeen v1).

설계 SSOT: `docs/nat-layer-design.md`. 결정(Uri): NAT를 먼저 진짜 계층으로 승격, 2주간 Memory Graph 금지.

원칙: Claude·Codex·Hermes·OMO·미래 에이전트의 *서로 다른 세계관*(Task=Prompt/Workflow/Goal)을 이 공통
타입으로 번역한다. Conductor는 실에이전트를 모르고(Identity NAT), 에이전트 자기보고 State는 신뢰하지 않는다
(Verifier=Gatekeeper). 이 모듈은 순수(IO·LLM 없음) — 결정론적·테스트 가능. agent-client는 필드명 맞춘 dict로
보내고 HQ가 pydantic 검증(runner.py 패턴).

씨앗 재사용: RunReport→Artifact, Gatekeeper→Verifier, ScopeClaims→Permission, task.status→State.
빠진 것(이번 작업): Artifact 1급화(최우선), Identity/Event NAT.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid

# ── State NAT — 모든 에이전트 상태를 5개로 번역(thinking/reflecting/working → RUNNING 등) ──
AgentState = Literal["PENDING", "RUNNING", "BLOCKED", "DONE", "FAILED"]

# ── Event NAT — 실시간 협업용 공통 이벤트(thinking/reflecting/reviewing → WORKING) ──
EventKind = Literal["STARTED", "WORKING", "BLOCKED", "WAITING_HUMAN", "DONE", "FAILED", "CANCELLED"]

# ── Artifact NAT — code_patch/skill/review_result 전부 Artifact(비평가: State보다 이게 최우선) ──
ArtifactType = Literal[
    "code_patch",      # claude git diff / omo edit
    "skill",           # hermes/omo가 만든 스킬
    "review_result",   # omo Review 단계 산출
    "decision",        # 의사결정(Memory NAT의 단위)
    "file",            # 일반 파일 산출
    "log",             # 실행 로그 tail
]


class AgentAddress(BaseModel):
    """Identity NAT — `agent://{role}/{specialty}`. Conductor는 이 주소만 알고 실에이전트(Claude/Hermes/…)는 모른다.

    해석(주소→실노드)은 identity_nat 서비스가 런타임에 한다. 오늘 Claude, 내일 Hermes, 1년 뒤 GPT-8이어도
    주소는 불변 → 에이전트 교체 가능.
    """
    role: str                       # frontend | backend | research | qa | pm
    specialty: Optional[str] = None

    @property
    def uri(self) -> str:
        return f"agent://{self.role}" + (f"/{self.specialty}" if self.specialty else "")

    @classmethod
    def parse(cls, uri: str) -> "AgentAddress":
        body = uri.removeprefix("agent://")
        role, _, spec = body.partition("/")
        return cls(role=role, specialty=spec or None)


AcceptanceKind = Literal[
    "file_exists",        # target 경로가 생성/수정됨(changed_files에 존재)
    "gitdiff_nonempty",   # 실제 변경이 있음(빈 diff = 거짓 done 차단)
    "test_passes",        # target 검증명령(checks[target]=="pass")
    "artifact_type",      # target 타입 Artifact가 1개 이상 생성됨
]


class AcceptanceCriterion(BaseModel):
    """Task NAT의 *검증가능* 완료 기준(구조화). Verifier(Gatekeeper)가 RunReport 데이터로 기계검증한다.
    에이전트 종류와 무관 — Claude든 OMO든 같은 기준으로 판정(이게 NAT의 핵심).
    """
    kind: AcceptanceKind
    target: Optional[str] = None                 # 경로 / 검증명령 이름 / Artifact 타입
    detail: Optional[str] = None


class NatTask(BaseModel):
    """Task NAT — 에이전트가 자기 방식으로 해석할 *의미*. Claude=Prompt, OMO=Workflow, Hermes=Goal로 해석하되
    Conductor는 의미를 모른다. acceptance는 Verifier가 기계검증할 *검증가능* 기준(구조화).
    """
    task_id: str
    intent: str                                  # "build login page" — 무엇을(자연어 의도)
    constraints: list[str] = Field(default_factory=list)   # 경계/제약(ScopeClaims로 정제됨)
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    target_address: Optional[str] = None         # agent://frontend (Identity NAT, Stage 3). 없으면 role 라우팅.
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Artifact(BaseModel):
    """Artifact NAT — 모든 산출물의 1급 공통 표현. Memory Graph는 Task가 아니라 *이것* 중심(비평가 교정)."""
    artifact_id: str = Field(default_factory=lambda: f"A-{uuid.uuid4().hex[:12]}")
    type: ArtifactType
    producer: str                                # agent://frontend (어느 가상 에이전트가 만들었나)
    task_id: str
    content_ref: Optional[str] = None            # 경로/URI/diff 참조(내용 자체는 별도 저장 — org는 결과만)
    summary: str = ""                            # 한 줄 요약(decision의 경우 reason 포함)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NatEvent(BaseModel):
    """Event NAT — 에이전트 native 이벤트(thinking/reflecting/reviewing)를 공통 enum으로 번역해 실시간 방송."""
    event: EventKind
    producer: str                                # agent://… 또는 agent_id
    task_id: Optional[str] = None
    detail: str = ""                             # native 상태 원문(디버그용, 신뢰 안 함)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NatRunResult(BaseModel):
    """AgentContract.run 완료 시 공통 결과 — Verifier(Gatekeeper) 입력. State는 자기보고(신뢰 X)."""
    task_id: str
    producer: str
    state: AgentState                            # 에이전트 자기보고 — Verifier가 재판정
    artifacts: list[Artifact] = Field(default_factory=list)
    completion_promise: Optional[str] = None     # "DONE" 선언 — Gatekeeper가 artifact/diff/test와 AND
    blockers: list[str] = Field(default_factory=list)
    trace_id: Optional[str] = None


_RUNNER_STATE: dict[str, AgentState] = {
    "done": "DONE", "error": "FAILED", "cancelled": "FAILED",
    "running": "RUNNING", "in_progress": "RUNNING", "pending": "PENDING",
    "blocked": "BLOCKED", "needs_review": "BLOCKED", "rejected": "FAILED",
}


def to_agent_state(runner_status: str) -> AgentState:
    """State NAT — 러너 native status(thinking/running/reflecting/…)를 공통 5-state로 번역."""
    return _RUNNER_STATE.get((runner_status or "").lower(), "FAILED")


def to_artifacts(run_report: dict, producer: str) -> list[Artifact]:
    """Artifact NAT — RunReport(changed_files/key_decisions)를 1급 Artifact[]로 번역(에이전트 무관).

    Claude git diff·OMO edit·Hermes skill 전부 같은 Artifact 모양으로. Memory Graph는 *이것* 위에 쌓인다
    (비평가 교정: Task 아니라 Artifact 중심). code_patch(파일변경) + decision(key_decisions).
    """
    task_id = run_report.get("task_id", "")
    arts: list[Artifact] = []
    for f in (run_report.get("changed_files") or []):
        arts.append(Artifact(type="code_patch", producer=producer, task_id=task_id,
                             content_ref=f, summary=f))
    for d in (run_report.get("key_decisions") or []):
        arts.append(Artifact(type="decision", producer=producer, task_id=task_id, summary=str(d)))
    return arts


def _passed(v: object) -> bool:
    return v in (True, "pass", "ok", "passed", 0, "0")


def check_acceptance(
    criteria: list[AcceptanceCriterion],
    *,
    changed_files: Optional[list[str]] = None,
    checks: Optional[dict] = None,
    artifacts: Optional[list[Artifact]] = None,
) -> tuple[bool, list[str]]:
    """Verifier 코어 — acceptance를 RunReport 데이터로 *기계검증*한다(순수, HQ, IO 없음).

    "State 신뢰 금지"의 실체: 에이전트가 DONE이라 *선언*해도, 이 함수가 acceptance를 충족하지 못하면 거짓.
    에이전트 종류(Claude/OMO/Hermes) 무관 **동일 판정** — 이게 NAT의 핵심. 반환: (전부통과?, 실패사유[]).
    """
    changed = [f.replace("\\", "/") for f in (changed_files or [])]
    checks = checks or {}
    arts = artifacts or []
    failures: list[str] = []

    for c in criteria:
        if c.kind == "gitdiff_nonempty":
            if not changed:
                failures.append("gitdiff_nonempty: 변경 파일 없음")
        elif c.kind == "file_exists":
            t = (c.target or "").replace("\\", "/")
            if not t or not any(f == t or f.endswith(t) for f in changed):
                failures.append(f"file_exists: {c.target} 미생성/미변경")
        elif c.kind == "test_passes":
            key = c.target or ""
            if key not in checks:
                failures.append(f"test_passes: {key} 검증 미실행")
            elif not _passed(checks.get(key)):
                failures.append(f"test_passes: {key} 실패")
        elif c.kind == "artifact_type":
            if not any(a.type == c.target for a in arts):
                failures.append(f"artifact_type: {c.target} 산출물 없음")
        else:
            failures.append(f"unknown acceptance kind: {c.kind}")

    return (len(failures) == 0, failures)
