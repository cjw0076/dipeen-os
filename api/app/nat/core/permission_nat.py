"""Permission NAT (M7 / Core) — agent 요청 → policy 분류 → ledger 기록 → 승인 시 permission.execute enqueue.

**Core는 실행하지 않는다.** 승인된 command를 *로컬 worker*가 pull해 LocalPermissionGuard 통과 후 실행한다.
Hard Deny=즉시 rejected(audit) / Auto Allow=즉시 execute enqueue / Human Approval=대기→approve 시 enqueue.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import Command, Event, PermissionRequest
from . import policy
from .command_queue import CommandQueue
from .eventlog import EventLog
from .permission_ledger import PermissionLedger


def _audit(store_root, event_type: str, req: PermissionRequest, message: str = "") -> None:
    EventLog(store_root).append(Event(
        event_type=event_type, task_id=req.task_id, run_id=req.run_id, producer="dipeen://core",
        message=message, payload={"permission_id": req.permission_request_id, "action": req.action}))


def _enqueue_execute(queue: CommandQueue, req: PermissionRequest) -> Command:
    """승인된 요청을 permission.execute command로 — 로컬 worker가 실행(Core 아님)."""
    return queue.enqueue(Command(
        command_type="permission.execute", task_id=req.task_id, run_id=req.run_id, provider="",
        permission_id=req.permission_request_id,
        required_capabilities=[f"executor.{req.action}"],
        workspace_root=req.workspace_root,
        payload={"action": req.action, "target": req.target, **(req.payload or {})}))


def submit_request(req: PermissionRequest, *, ledger: PermissionLedger, queue: CommandQueue,
                   store_root: str) -> PermissionRequest:
    """policy 분류 → ledger. deny=rejected(audit), auto=approved+execute enqueue, human=requested(대기)."""
    decision = policy.classify(req.action)
    req.policy_decision = decision
    if decision == "deny":
        req.state = "rejected"
        ledger.save(req)
        _audit(store_root, "permission.rejected", req, "policy_violation: hard deny")
        return req
    _audit(store_root, "permission.requested", req)
    if decision == "auto_allow":
        req.state = "approved"
        ledger.save(req)
        _enqueue_execute(queue, req)
    else:                                       # require_human_approval (또는 manual_handoff)
        req.state = "requested"
        ledger.save(req)
    return req


# 실제 worker 실행이 필요한 side-effect action(승인 시 permission.execute enqueue). 나머지(workspace.* 등
# review gate)는 승인만 — 실행할 게 없다(작업은 이미 sandbox에서 끝남).
_EXECUTABLE = {"git.commit", "git.push", "github.issue.create", "github.pr.create"}


def approve(permission_id: str, *, decider: str, ledger: PermissionLedger,
            queue: CommandQueue) -> Optional[Command]:
    """사람 승인 → state=approved. side-effect action이면 permission.execute enqueue(Core는 실행 안 함).
    idempotent: 이미 결정된 요청은 None. hard deny action은 승인 불가(정책 재검사)."""
    req = ledger.get(permission_id)
    if req is None or req.state != "requested":     # idempotency: 이미 approved/rejected면 재실행 X
        return None
    if policy.classify(req.action) == "deny":        # hard deny는 승인해도 실행 불가 → reject
        req.state = "rejected"
        req.decided_by = decider
        ledger.save(req)
        _audit(ledger.root, "permission.rejected", req, "policy_violation: hard deny — 승인 불가")
        return None
    req.state = "approved"
    req.decided_by = decider
    ledger.save(req)
    _audit(ledger.root, "permission.approved", req, f"approved by {decider}")
    if req.action in _EXECUTABLE:                    # 실행 필요한 side-effect만 command 생성
        return _enqueue_execute(queue, req)
    return None                                      # review gate — 승인만(command 없음)


def reject(permission_id: str, *, ledger: PermissionLedger, reason: str = "") -> Optional[PermissionRequest]:
    req = ledger.get(permission_id)
    if req is None:
        return None
    req.state = "rejected"
    ledger.save(req)
    _audit(ledger.root, "permission.rejected", req, reason or "rejected by human")
    return req
