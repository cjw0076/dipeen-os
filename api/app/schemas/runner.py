"""Runner 계약 (W0) — Dipeen이 소유하는 wrap 경계.

원칙(`docs/dipeen-wrap-principle.md`): 경계는 HQ, 루프는 runner, truth는 HQ만.
이 모듈은 omo/hermes/claude-code를 fork 없이 wrap하기 위해 HQ가 고정하는 3+1 계약:
  - TaskEnvelope  : HQ → Node (무엇을, 어떤 *경계* 안에서)
  - RunReport     : Node → HQ (무엇을 실제로 했나)
  - GatekeeperVerdict : 출구 게이트 (범위 안에서·검증 통과했나)
  - scope_claims  : 결정 카드(entry gate)와 Gatekeeper(exit gate)를 잇는 단일 계약.

decision 카드(brief approve)가 scope_claims를 *정의*하고, Gatekeeper가 *지켜졌는지* 검증한다.
runner가 scope를 넘으면 Gatekeeper가 needs_human=True로 다시 카드를 띄운다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
import uuid

RunnerName = Literal["claude-code", "omo-opencode", "omo-codex-light", "hermes"]

# 실패 분류(failure-recovery §4). "엣지케이스 나열" 대신 *유한한 범주*로 접는다.
# RemediationPolicy가 이 코드를 action(retry|needs_human|...)에 매핑한다(LLM 아님).
FailureCode = Literal[
    "NONE",               # accept
    "SCOPE_VIOLATION",    # 허용 경로 밖 편집 → needs_human
    "PROMISE_FALSE",      # DONE 거짓(promise 미충족) → reject+retry
    "DETERMINISTIC_FAIL", # pytest/ruff 실패 → reject+retry(checks 첨부)
    "RUNNER_ERROR",       # subprocess/도구 오류 → 다른 runner / HITL
    "TIMEOUT",            # 시간 초과 → 재배정/scope 축소
    "STALE_EDIT",         # hashline mismatch(omo) → 파일 스니펫 첨부 retry
    "AMBIGUOUS_DONE",     # 일부만 완료 → wave 분해(PM)
    "HITL_REQUIRED",      # 고위험 → 결정 카드 재표시
    "CANCELLED",          # 사용자/PM 취소 → 재개 없음
    "UNKNOWN",            # 처음 보는 실패 → fail-closed(needs_human)
]


class ScopeClaims(BaseModel):
    """결정 카드가 고정하는 *경계*. runner는 이 안에서만 자유롭게 루프한다."""
    allow_paths: list[str] = Field(default_factory=list, description="편집 허용 경로/glob (빈 리스트=workspace 전체)")
    deny_paths: list[str] = Field(default_factory=list, description="절대 금지 경로 (.env, secrets 등)")
    allow_actions: list[str] = Field(default_factory=lambda: ["read", "edit", "test"], description="read|edit|run|test|net")
    max_files: Optional[int] = Field(None, description="변경 가능한 최대 파일 수 (초과 시 human gate)")
    requires_human_approval: bool = Field(False, description="결과를 사람이 반드시 승인해야 하나(고위험)")


class TaskEnvelope(BaseModel):
    """HQ → Node. PM이 만든 태스크 + 결정 카드가 고정한 경계."""
    v: int = 1
    task_id: str
    team_id: str
    room_id: str = "general"
    assigned_agent_id: Optional[str] = None
    runner: RunnerName = "claude-code"          # 노드의 roster 설정에서
    subject: str
    prompt: str                                  # 6섹션 위임 본문 (MUST_DO/MUST_NOT 포함)
    completion_promise: str = "DONE"
    branch: Optional[str] = None
    blocked_by: list[str] = Field(default_factory=list)
    workspace_root: Optional[str] = None         # Node 로컬 경로
    context_refs: list[str] = Field(default_factory=list, description="HQ가 참조한 파일 경로 힌트")
    decision_id: Optional[str] = None            # 이 태스크를 승인한 결정 카드 id (entry gate)
    scope_claims: ScopeClaims = Field(default_factory=ScopeClaims)
    attempt: int = 1                             # remediation 재시도 번호 (1=최초). trace_id로 체인 추적.
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 회의→배정→실행 추적


class RunReport(BaseModel):
    """Node → HQ. runner가 실제로 한 일 (Gatekeeper 입력)."""
    v: int = 1
    task_id: str
    agent_id: str
    runner: RunnerName
    status: Literal["done", "error", "cancelled"]
    completion_promise: Optional[str] = None     # "DONE" 여부 (runner 자기보고 — 신뢰 X, Gatekeeper가 판정)
    changed_files: list[str] = Field(default_factory=list)
    scope_diff: list[str] = Field(default_factory=list, description="실제로 만진 경로 — scope_claims와 대조")
    key_decisions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    tests_run: Optional[str] = None
    artifacts_uri: Optional[str] = None          # .dipeen-result.json 요약
    log_stream_tail: Optional[str] = None        # Spine LOG_STREAM 마지막 N줄
    duration_ms: Optional[int] = None
    trace_id: Optional[str] = None


class GatekeeperVerdict(BaseModel):
    """출구 게이트 결과. runner 자기보고가 아니라 HQ가 판정."""
    task_id: str
    verdict: Literal["accept", "reject", "needs_human"]
    failure_code: FailureCode = "NONE"   # 무엇이 실패했나(분류). RemediationPolicy의 키.
    deterministic_checks: dict[str, Any] = Field(default_factory=dict, description="{pytest: pass, ruff: pass, ...}")
    scope_violations: list[str] = Field(default_factory=list, description="scope_claims 위반 (claimed vs scope_diff)")
    reason: Optional[str] = None
    # needs_human → HQ가 결정 카드(exit)를 다시 사람에게 띄운다 (카드 재사용)
    human_card_prompt: Optional[str] = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
