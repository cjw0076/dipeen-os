"""Reconciler (M4 / §11) — claim + verification + permission + acceptance → 최종 TaskState.

StateClaim(agent 주장) ≠ TaskState(Dipeen 결정). **증거 우선**: acceptance가 충족이면 claim 무관 DONE;
claim done인데 미충족이면 거짓 done → NEEDS_RETRY. 권한 대기는 side-effect 전 최우선(gatekeeper needs_human 선례).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..contracts import (
    Artifact, FailureType, PermissionRequest, StateClaim, TaskEnvelope, TaskState,
)
from .verifier import check_acceptance, has_deliverable, verify_artifacts


@dataclass
class ReconcileResult:
    state: TaskState
    failure_type: Optional[FailureType] = None
    reasons: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)   # verified 사본(Store 영속용)


def reconcile(task: TaskEnvelope, *, claims: list[StateClaim], artifacts: list[Artifact],
              checks: Optional[dict] = None,
              permissions: Optional[list[PermissionRequest]] = None) -> ReconcileResult:
    """증거로 TaskState 결정. AWAITING_PERMISSION / DONE / BLOCKED / FAILED / NEEDS_RETRY."""
    permissions = permissions or []

    # 1) 권한 대기 우선 — 승인 전 side-effect 금지
    if any(p.state == "requested" and p.requires_human_approval for p in permissions):
        return ReconcileResult("AWAITING_PERMISSION", reasons=["권한 승인 대기"])

    verified = verify_artifacts(artifacts)
    ok, failures = check_acceptance(task, artifacts=verified, checks=checks)

    # 2) 증거 우선 — acceptance 충족이면 claim 무관 DONE
    if ok:
        return ReconcileResult("DONE", artifacts=verified)

    # 3) acceptance 미충족 — agent claim으로 분기
    claimed = claims[-1].claimed_state if claims else None
    if claimed == "blocked":
        return ReconcileResult("BLOCKED", reasons=failures or ["agent blocked"], artifacts=verified)
    if claimed == "needs_input":
        return ReconcileResult("BLOCKED", reasons=["needs human input"], artifacts=verified)
    if claimed == "failed":
        return ReconcileResult("FAILED", failure_type="agent_crash",
                               reasons=failures or ["agent failed"], artifacts=verified)

    # claimed done/working/None + acceptance 실패 → 거짓 done → NEEDS_RETRY
    ft: FailureType = "acceptance_not_met" if has_deliverable(verified) else "artifact_missing"
    return ReconcileResult("NEEDS_RETRY", failure_type=ft, reasons=failures, artifacts=verified)
