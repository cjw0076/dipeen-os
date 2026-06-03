"""CommandProposal (M8 / Core) — message↔실행 사이의 안전 경계.

**채팅이 바로 실행되지 않는다.** message가 작업을 함의해도 즉시 실행하지 않고 CommandProposal을 만든다(제안).
사람/정책이 confirm해야만 conductor가 run.start command를 enqueue한다. reject면 아무 일도 없음.
`message.created → command.proposed → (confirm) → command.queued`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contracts import AssignmentSpec, Command, CommandProposal, Event, TaskEnvelope
from . import conductor
from .command_queue import CommandQueue
from .eventlog import EventLog
from .routing import assignment_to_capabilities


class ProposalStore:
    def __init__(self, store_root: str | Path):
        self.dir = Path(store_root) / "proposals"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, proposal_id: str) -> Path:
        return self.dir / f"{proposal_id}.json"

    def save(self, p: CommandProposal) -> CommandProposal:
        self._path(p.proposal_id).write_text(p.model_dump_json(indent=2), encoding="utf-8")
        return p

    def get(self, proposal_id: str) -> Optional[CommandProposal]:
        p = self._path(proposal_id)
        return CommandProposal.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def all(self) -> list[CommandProposal]:
        return [CommandProposal.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.dir.glob("PROP-*.json"))]


def propose_command(*, room_id: str, intent: str, provider: str, workspace_root: str,
                    proposed_by: str, store_root: str, message_id: Optional[str] = None,
                    acceptance: Optional[list] = None,
                    assignment: Optional[AssignmentSpec] = None) -> CommandProposal:
    """message가 함의한 작업을 *제안*으로 만든다. **enqueue하지 않는다** — confirm 전엔 실행 없음.
    assignment(역할/사람/repo/worker)는 confirm 시 required_capabilities로 변환돼 라우팅된다."""
    p = CommandProposal(room_id=room_id, message_id=message_id, proposed_by=proposed_by,
                        intent=intent, provider=provider, workspace_root=workspace_root,
                        assignment=assignment, acceptance=acceptance or [])
    ProposalStore(store_root).save(p)
    EventLog(store_root).append(Event(event_type="decision.proposed", producer=proposed_by,
                                      message=f"command proposal: {intent[:80]}",
                                      payload={"proposal_id": p.proposal_id, "room_id": room_id}))
    return p


def propose_plan(plan: list[dict], *, room_id: str, store_root: str,
                 proposed_by: str) -> list[CommandProposal]:
    """plan(여러 step)을 CommandProposal[]로 — **pm_loop 강등**: PM은 *제안만*, 실행은 confirm 후.
    step = {intent, provider?, workspace_root?, acceptance?, assignment?}. 어느 것도 enqueue하지 않는다."""
    def _asg(step):
        a = step.get("assignment")
        return AssignmentSpec.model_validate(a) if isinstance(a, dict) else a
    return [propose_command(
        room_id=room_id, intent=step["intent"], provider=step.get("provider", "claude"),
        workspace_root=step.get("workspace_root", ""), proposed_by=proposed_by, store_root=store_root,
        acceptance=step.get("acceptance"), assignment=_asg(step)) for step in plan]


def confirm_proposal(proposal_id: str, *, decided_by: str, queue: CommandQueue,
                     store_root: str) -> Optional[Command]:
    """사람/정책 confirm → conductor가 run.start enqueue. 여기서 *비로소* 실행 경로에 들어간다."""
    store = ProposalStore(store_root)
    p = store.get(proposal_id)
    if p is None or p.state != "proposed":
        return None
    task = TaskEnvelope(title=p.intent[:48], intent=p.intent, acceptance=p.acceptance)
    # 배정 → required_capabilities + workspace_ref. 맞는 worker만 lease(HQ push 아님). 없으면 풀 라우팅(하위호환).
    caps = assignment_to_capabilities(p.assignment, provider=p.provider) if p.assignment else None
    ws_ref = p.assignment.workspace_ref if p.assignment else None
    repo_ns = None
    if p.assignment and p.assignment.repo:
        r = p.assignment.repo
        repo_ns = r if r.startswith("repo.") else f"repo.{r}"
    cmd = conductor.dispatch_run(queue, task, provider=p.provider, workspace_root=p.workspace_root,
                                 store_root=store_root, required_capabilities=caps,
                                 workspace_ref=ws_ref, repo=repo_ns)
    p.state = "confirmed"
    p.decided_by = decided_by
    p.task_id = task.task_id
    p.command_id = cmd.command_id
    store.save(p)
    EventLog(store_root).append(Event(event_type="decision.accepted", producer=decided_by, task_id=task.task_id,
                                      message="proposal confirmed → enqueued",
                                      payload={"proposal_id": proposal_id, "command_id": cmd.command_id}))
    return cmd


def reject_proposal(proposal_id: str, *, decided_by: str, store_root: str) -> Optional[CommandProposal]:
    store = ProposalStore(store_root)
    p = store.get(proposal_id)
    if p is None:
        return None
    p.state = "rejected"
    p.decided_by = decided_by
    store.save(p)
    EventLog(store_root).append(Event(event_type="decision.voted", producer=decided_by,
                                      message="proposal rejected", payload={"proposal_id": proposal_id}))
    return p
