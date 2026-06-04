"""Canonical control-plane store helpers.

This module exposes the NAT event-sourced stores as UI-readable resources.
It intentionally stays thin: provider runtimes still emit raw output/claims,
while Dipeen records normalized runs, events, artifacts, state claims,
permission requests, and memory candidates.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from app.db.models import Agent, Task
from app.nat.contracts import (
    Artifact,
    ArtifactLocation,
    ArtifactProducer,
    AssignmentSpec,
    Command,
    CommandProposal,
    Event,
    EventType,
    Evidence,
    Message,
    MemoryCandidate,
    NormalizedAgentResult,
    PermissionRequest,
    Room,
    Run,
    StateClaim,
    TaskEnvelope,
    TaskScope,
    WorkerInfo,
)
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.command_queue import CommandQueue
from app.nat.core.eventlog import EventLog
from app.nat.core.ingest import ingest_result
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core import meeting, permission_nat, policy, proposals, routing
from app.nat.core.proposals import ProposalStore
from app.nat.core.rooms import MessageLog, RoomStore
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.schemas.agent import AgentReport


def _now() -> datetime:
    return datetime.now(timezone.utc)


def control_plane_root() -> Path:
    return Path(
        os.getenv("NAT_WORKSPACE")
        or Path(__file__).resolve().parents[3] / "nat-workspace"
    )


def _run_store() -> RunStore:
    return RunStore(control_plane_root())


def _event_log() -> EventLog:
    return EventLog(control_plane_root())


def _artifact_store() -> ArtifactStore:
    return ArtifactStore(control_plane_root())


def _command_queue() -> CommandQueue:
    return CommandQueue(control_plane_root())


def _room_store() -> RoomStore:
    return RoomStore(control_plane_root())


def _message_log() -> MessageLog:
    return MessageLog(control_plane_root())


def _proposal_store() -> ProposalStore:
    return ProposalStore(control_plane_root())


def _worker_registry() -> WorkerRegistry:
    return WorkerRegistry(control_plane_root())


def _permission_ledger() -> PermissionLedger:
    return PermissionLedger(control_plane_root())     # canonical permission store(JSONL 폐기)


def _jsonl_path(name: str) -> Path:
    path = control_plane_root() / "events" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(name: str, model: Any) -> None:
    with _jsonl_path(name).open("a", encoding="utf-8") as f:
        f.write(model.model_dump_json() + "\n")


def _read_jsonl(name: str, model_cls: type) -> list:
    path = _jsonl_path(name)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(model_cls.model_validate_json(line))
        except Exception:
            continue
    return out


def _write_jsonl(name: str, models: Iterable[Any]) -> None:
    path = _jsonl_path(name)
    with path.open("w", encoding="utf-8") as f:
        for model in models:
            f.write(model.model_dump_json() + "\n")


def _agent_identity(agent: Agent | None, *, fallback_role: str | None = None) -> str:
    role = (agent.role if agent else fallback_role) or "worker"
    role_slug = role.lower().replace(" ", "-")
    return f"agent://team/{role_slug}"


def _task_scope(task: Task) -> TaskScope:
    paths = []
    if task.branch:
        paths.append(task.branch)
    return TaskScope(repo=None, paths=paths)


def task_to_envelope(task: Task) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task.task_id,
        title=task.subject,
        intent=task.prompt,
        scope=_task_scope(task),
        constraints=[],
        dependencies=[task.blocked_by] if task.blocked_by else [],
        state="READY" if task.status == "pending" else "CREATED",
    )


def append_event(
    event_type: EventType,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    producer: str = "dipeen://core",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        event_type=event_type,
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        message=message,
        payload=payload or {},
    )
    return _event_log().append(event)


def list_rooms() -> list[Room]:
    return _room_store().list()


def get_room(room_id: str) -> Room | None:
    return _room_store().get(room_id)


def create_room(room: Room) -> Room:
    return _room_store().create(room)


def list_messages(room_id: str) -> list[Message]:
    return _message_log().read(room_id)


def post_message(message: Message) -> Message:
    return _message_log().post(message)


def list_proposals(*, room_id: str | None = None, state: str | None = None) -> list[CommandProposal]:
    items = _proposal_store().all()
    if room_id:
        items = [p for p in items if p.room_id == room_id]
    if state:
        items = [p for p in items if p.state == state]
    return sorted(items, key=lambda p: p.created_at, reverse=True)


def propose_command(
    *,
    room_id: str,
    intent: str,
    provider: str,
    workspace_root: str,
    proposed_by: str,
    message_id: str | None = None,
    acceptance: list | None = None,
    assignment: AssignmentSpec | dict | None = None,
) -> CommandProposal:
    if isinstance(assignment, dict):
        assignment = AssignmentSpec.model_validate(assignment)
    return proposals.propose_command(
        room_id=room_id,
        intent=intent,
        provider=provider,
        workspace_root=workspace_root,
        proposed_by=proposed_by,
        store_root=str(control_plane_root()),
        message_id=message_id,
        acceptance=acceptance,
        assignment=assignment,
    )


def close_meeting(room_id: str) -> dict:
    """회의방 메시지를 분류해 정리물(후보)을 만든다 — '정리' 버튼. **승인 전엔 작업 아님.**

    memory candidate는 리뷰 큐(JSONL)에 *영속*한다 — 생성만 하고 버리면 회의 결정이 조직기억으로 못 간다.
    **자동승격 아님**: status=pending으로 쌓고 사람이 promote(Org Memory 원칙). task/decision은 별도 승인 경로.
    """
    packet = meeting.close_meeting(room_id, _message_log().read(room_id))
    for mc in packet.memory_candidates:
        _append_jsonl("memory_candidates", mc)
    return packet.model_dump(mode="json")


def approve_action_candidate(candidate: dict, *, room_id: str, proposed_by: str = "user://web") -> CommandProposal:
    """승인된 작업 후보 → CommandProposal(배정 포함) → Assignment Routing/Workspace로 연결."""
    from app.nat.contracts import ActionCandidate
    cand = ActionCandidate.model_validate(candidate)
    return meeting.approve_action_candidate(cand, room_id=room_id, proposed_by=proposed_by,
                                            store_root=str(control_plane_root()))


def preview_routing(assignment: AssignmentSpec | dict | None, *, provider: str = "claude") -> dict:
    """배정 미리보기 — '이 작업은 누구에게 가는지'를 현재 등록된 worker 기준으로 계산(Assignment UI용)."""
    if isinstance(assignment, dict):
        assignment = AssignmentSpec.model_validate(assignment)
    return routing.preview_routing(assignment, provider=provider, workers=_worker_registry().all())


def propose_plan(plan: list[dict], *, room_id: str, proposed_by: str) -> list[CommandProposal]:
    return proposals.propose_plan(
        plan,
        room_id=room_id,
        store_root=str(control_plane_root()),
        proposed_by=proposed_by,
    )


def confirm_proposal(proposal_id: str, *, decided_by: str) -> Command | None:
    return proposals.confirm_proposal(
        proposal_id,
        decided_by=decided_by,
        queue=_command_queue(),
        store_root=str(control_plane_root()),
    )


def reject_proposal(proposal_id: str, *, decided_by: str) -> CommandProposal | None:
    return proposals.reject_proposal(
        proposal_id,
        decided_by=decided_by,
        store_root=str(control_plane_root()),
    )


async def mint_team_invite(team_id: str) -> dict:
    """Mint a fresh single-use invite (24h TTL). Returns {code, expires_at}.
    Replicates the teams invite core directly (no FastAPI Depends) so the
    capability layer (dipeen open / /dipeen invite) can mint without HTTP."""
    import secrets
    from datetime import datetime, timedelta, timezone

    from app.db.models import InviteCode
    from app.db.session import async_session
    from app.routers.teams import INVITE_TTL_SEC

    code = secrets.token_urlsafe(6)[:8].upper()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_TTL_SEC)
    async with async_session() as db:
        db.add(InviteCode(code=code, team_id=team_id, expires_at=expires_at))
        await db.commit()
    return {"code": code, "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")}


async def request_session_permission(reason: str) -> str:
    """Create a PENDING ``session.expose`` permission request (no tunnel — the API can't start a
    host-local tunnel). policy classifies session.expose as require_human_approval, so submit_request
    persists it as ``requested``; a human approves later with /dipeen approve. Returns the request id."""
    req = PermissionRequest(task_id="session", run_id="", requester="user://owner",
                            action="session.expose", reason=reason, risk="high")
    permission_nat.submit_request(req, ledger=_permission_ledger(), queue=_command_queue(),
                                  store_root=str(control_plane_root()))
    return req.permission_request_id


def list_workers() -> list[WorkerInfo]:
    return _worker_registry().all()


def register_worker(worker_id: str, capabilities: list[str], *, workspaces: list | None = None) -> WorkerInfo:
    # workspaces=list[dict] → WorkerInfo가 WorkerWorkspace[]로 coerce. local_path는 worker-local(HQ 디버그용).
    return _worker_registry().register(
        WorkerInfo(worker_id=worker_id, capabilities=capabilities, workspaces=workspaces or []))


def heartbeat_worker(worker_id: str) -> WorkerInfo | None:
    return _worker_registry().heartbeat(worker_id)


def list_commands(*, state: str | None = None) -> list[Command]:
    items = _command_queue()._all()
    if state:
        items = [c for c in items if c.state == state]
    return sorted(items, key=lambda c: c.created_at, reverse=True)


def get_command(command_id: str) -> Command | None:
    return _command_queue().get(command_id)


def poll_worker_command(worker_id: str, capabilities: list[str]) -> Command | None:
    _worker_registry().heartbeat(worker_id)
    return _command_queue().poll(worker_id, capabilities)


def ack_worker_command(worker_id: str, command_id: str) -> Command | None:
    return _command_queue().ack(command_id, worker_id)


def complete_worker_command(worker_id: str, command_id: str) -> Command | None:
    cmd = _command_queue().get(command_id)
    if not cmd or cmd.lease_owner != worker_id:
        return None
    return _command_queue().complete(command_id)


def fail_worker_command(worker_id: str, command_id: str) -> Command | None:
    cmd = _command_queue().get(command_id)
    if not cmd or cmd.lease_owner != worker_id:
        return None
    return _command_queue().fail(command_id)


def ingest_worker_command_result(
    *,
    worker_id: str,
    command_id: str,
    status: str,
    summary: str = "",
    changed_files: list[str] | None = None,
    tests_passed: bool = False,
    pr_url: str | None = None,
    key_decisions: list[str] | None = None,
    runner: str | None = None,
) -> dict[str, Any] | None:
    queue = _command_queue()
    cmd = queue.get(command_id)
    if not cmd or cmd.lease_owner != worker_id or cmd.task is None:
        return None
    if cmd.state == "leased":
        queue.ack(command_id, worker_id)

    task = cmd.task
    producer = ArtifactProducer(
        identity=f"dipeen://worker/{worker_id}",
        adapter=runner or cmd.provider,
        provider=cmd.provider,
    )
    files = changed_files or []
    artifacts: list[Artifact] = []
    if files:
        artifacts.append(Artifact(
            type="code_patch",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer,
            title="Code patch",
            summary=f"{len(files)} changed files reported by worker.",
            locations=[ArtifactLocation(uri=f"workspace://{path}") for path in files],
            evidence=[Evidence(kind="git_diff_exists", passed=True)],
        ))
        artifacts.append(Artifact(
            type="file_change_set",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer,
            title="Changed files",
            summary=f"{len(files)} files changed",
            locations=[ArtifactLocation(uri=f"workspace://{path}") for path in files],
            evidence=[Evidence(kind="file_change_reported", passed=True)],
        ))
    artifacts.append(Artifact(
        type="test_report",
        task_id=task.task_id,
        run_id=cmd.run_id,
        producer=producer,
        title="Worker test report",
        summary=summary or ("Tests passed" if tests_passed else "Worker did not verify tests."),
        evidence=[Evidence(kind="tests_passed", passed=tests_passed)],
    ))
    if key_decisions:
        artifacts.append(Artifact(
            type="review_result",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer,
            title="Worker decisions",
            summary="; ".join(key_decisions[:3]),
            evidence=[Evidence(kind="decision_distilled", passed=True)],
        ))
    if pr_url:
        artifacts.append(Artifact(
            type="pr_reference",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer,
            title="Pull request",
            summary=pr_url,
            locations=[ArtifactLocation(uri=pr_url, media_type="text/uri-list")],
            evidence=[Evidence(kind="pr_url_reported", passed=True)],
        ))

    raw = status.lower()
    claimed_state = "done" if raw in ("done", "completed", "success") else "failed"
    if raw in ("blocked", "needs_input"):
        claimed_state = "blocked" if raw == "blocked" else "needs_input"
    claim = StateClaim(
        task_id=task.task_id,
        run_id=cmd.run_id,
        producer=producer.identity,
        claimed_state=claimed_state,
        message=summary,
    )
    events = [
        Event(
            event_type="agent.started",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer.identity,
            message=f"worker result received: {status}",
        ),
        Event(
            event_type="state.claimed",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer.identity,
            message=summary,
            payload={"claimed_state": claimed_state},
        ),
    ]
    for artifact in artifacts:
        events.append(Event(
            event_type="artifact.produced",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer.identity,
            message=artifact.title,
            payload={"artifact_id": artifact.artifact_id, "artifact_type": artifact.type},
        ))
    normalized = NormalizedAgentResult(
        artifacts=artifacts,
        events=events,
        state_claims=[claim],
    )
    result = ingest_result(task, run_id=cmd.run_id, normalized=normalized, store_root=str(control_plane_root()))
    _append_jsonl("state_claims", claim)
    for decision in key_decisions or []:
        candidate = MemoryCandidate(
            memory_type="project_decision",
            proposed_content=decision,
            confidence=0.66,
        )
        _append_jsonl("memory_candidates", candidate)
        append_event(
            "memory.candidate_created",
            task_id=task.task_id,
            run_id=cmd.run_id,
            producer=producer.identity,
            message=decision,
            payload={"memory_candidate_id": candidate.memory_candidate_id},
        )
    queue.complete(command_id)
    return {"command": queue.get(command_id), "result": result}


def ingest_permission_result(
    *,
    worker_id: str,
    command_id: str,
    artifact: dict[str, Any],
    permission_id: str | None = None,
    executed: bool = False,
) -> dict[str, Any] | None:
    """worker가 permission.execute를 처리하고 올린 receipt를 영속·reconcile + ledger 갱신 + command 완료.

    **Core는 실행하지 않는다** — worker가 자기 PC에서 dry_run/manual/local_execute로 결정·실행하고
    receipt(증거)만 올린다. 기본 dry_run이면 would_execute 미리보기일 뿐 진짜 PR/push는 없다.
    """
    queue = _command_queue()
    cmd = queue.get(command_id)
    if not cmd or cmd.lease_owner != worker_id:        # 점유자만 결과 제출(위조 방지)
        return None
    if cmd.state == "leased":
        queue.ack(command_id, worker_id)

    receipt = Artifact.model_validate(artifact)
    action = (cmd.payload or {}).get("action", "")
    events = [Event(
        event_type="permission.executed",
        task_id=cmd.task_id, run_id=cmd.run_id,
        producer=f"dipeen://worker/{worker_id}",
        message=f"{action} ({'executed' if executed else 'preview/handoff'})",
        payload={"permission_id": permission_id, "executed": executed,
                 "artifact_id": receipt.artifact_id},
    )]
    task = _run_store().load_task(cmd.task_id)
    result = (ingest_result(task, run_id=cmd.run_id,
                            normalized=NormalizedAgentResult(artifacts=[receipt], events=events),
                            store_root=str(control_plane_root())) if task else None)
    if task is None:                                   # task 없으면 ingest_result 미경유 → 직접 영속
        _artifact_store().save(receipt)
        for ev in events:
            _event_log().append(ev)

    if permission_id:                                  # ledger 갱신(dry_run/handoff=approved, 실제 실행=executed)
        led = _permission_ledger()
        req = led.get(permission_id)
        if req:
            req.state = "executed" if executed else "approved"
            led.save(req)

    queue.complete(command_id)
    return {
        "command": queue.get(command_id),
        "state": result.state if result else None,
        "artifact_id": receipt.artifact_id,
        "executed": executed,
    }


def ingest_probe_result(
    *,
    worker_id: str,
    command_id: str,
    probe: dict[str, Any],
) -> dict[str, Any] | None:
    """worker가 provider read-only probe(doctor/status)를 실행해 올린 결과를 task-less Event로 영속 + command 완료.

    **Core는 실행하지 않는다** — worker가 자기 PC에서 provider CLI를 read-only로 돌리고 결과만 올린다.
    probe는 task 라이프사이클 밖이라 reconcile 없이 EventLog에 직접 append한다(permission task-less 분기 미러).
    """
    queue = _command_queue()
    cmd = queue.get(command_id)
    if not cmd or cmd.lease_owner != worker_id:        # 점유자만 결과 제출(위조 방지)
        return None
    if cmd.state == "leased":
        queue.ack(command_id, worker_id)
    ev = Event(
        event_type="provider.probed", task_id=None, run_id=None,
        producer=f"dipeen://worker/{worker_id}",
        message=f"probe {probe.get('provider')} (exit={probe.get('exit')})",
        payload={"provider": probe.get("provider"), "exit": probe.get("exit"),
                 "stdout": (probe.get("stdout") or "")[:4000], "stderr": (probe.get("stderr") or "")[:2000]},
    )
    _event_log().append(ev)
    queue.complete(command_id)
    return {"command": queue.get(command_id), "event_id": ev.event_id, "provider": probe.get("provider")}


def record_task_created(task: Task) -> Event:
    _run_store().save_task(task_to_envelope(task))
    return append_event(
        "task.created",
        task_id=task.task_id,
        message=task.subject,
        payload={"status": task.status, "required_role": task.required_role},
    )


def record_task_state(task: Task, *, event_type: EventType | None = None) -> Event:
    state_map = {
        "pending": "READY",
        "in_progress": "RUNNING",
        "blocked": "BLOCKED",
        "done": "DONE",
        "error": "FAILED",
        "rejected": "REJECTED",
        "needs_review": "AWAITING_PERMISSION",
        "cancelled": "CANCELLED",
    }
    stored = _run_store().load_task(task.task_id) or task_to_envelope(task)
    stored.state = state_map.get((task.status or "").lower(), stored.state)
    _run_store().save_task(stored)
    return append_event(
        event_type or ("task.completed" if task.status == "done" else "state.reconciled"),
        task_id=task.task_id,
        message=f"Task reconciled to {task.status}",
        payload={"status": task.status, "pr_url": task.pr_url},
    )


def _changed_file_artifact(
    *,
    task_id: str,
    run_id: str,
    producer: ArtifactProducer,
    changed_files: list[str],
) -> Artifact | None:
    if not changed_files:
        return None
    return Artifact(
        type="file_change_set",
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        title="Changed files",
        summary=f"{len(changed_files)} files changed",
        locations=[ArtifactLocation(uri=f"workspace://{path}") for path in changed_files],
        evidence=[Evidence(kind="file_change_reported", passed=True)],
    )


def _code_patch_artifact(
    *,
    task_id: str,
    run_id: str,
    producer: ArtifactProducer,
    changed_files: list[str],
) -> Artifact | None:
    if not changed_files:
        return None
    return Artifact(
        type="code_patch",
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        title="Code patch",
        summary="Provider reported a code patch.",
        locations=[ArtifactLocation(uri=f"workspace://{path}") for path in changed_files],
        evidence=[Evidence(kind="git_diff_exists", passed=True)],
    )


def _test_report_artifact(
    *,
    task_id: str,
    run_id: str,
    producer: ArtifactProducer,
    report: AgentReport,
) -> Artifact:
    checks = report.artifacts.checks if report.artifacts else {}
    passed = bool(report.tests_passed) or all(v in ("pass", "ok", "passed", True, 0, "0") for v in checks.values())
    return Artifact(
        type="test_report",
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        title="Test report",
        summary=report.summary or ("Tests passed" if passed else "Tests not fully verified"),
        evidence=[Evidence(kind="tests_passed", passed=passed, message=json.dumps(checks, ensure_ascii=False))],
    )


def _review_artifact(
    *,
    task_id: str,
    run_id: str,
    producer: ArtifactProducer,
    decisions: list[str],
) -> Artifact | None:
    if not decisions:
        return None
    return Artifact(
        type="review_result",
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        title="Key decisions",
        summary="; ".join(decisions[:3]),
        evidence=[Evidence(kind="decision_distilled", passed=True)],
    )


def _pr_artifact(
    *,
    task_id: str,
    run_id: str,
    producer: ArtifactProducer,
    pr_url: str | None,
) -> Artifact | None:
    if not pr_url:
        return None
    return Artifact(
        type="pr_reference",
        task_id=task_id,
        run_id=run_id,
        producer=producer,
        title="Pull request",
        summary=pr_url,
        locations=[ArtifactLocation(uri=pr_url, media_type="text/uri-list")],
        evidence=[Evidence(kind="pr_url_reported", passed=True)],
    )


def record_agent_report(
    *,
    agent: Agent,
    task: Task,
    report: AgentReport,
    effective_status: str,
    gatekeeper_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist normalized run evidence from the existing report endpoint."""
    run_store = _run_store()
    identity_id = _agent_identity(agent)
    attempt = run_store.next_attempt(task.task_id)
    run = Run(
        task_id=task.task_id,
        identity_id=identity_id,
        attempt=attempt,
        state="CLOSED",
        failure_type=None if effective_status == "done" else "invalid_output",
    )
    run_store.save_run(run)

    producer = ArtifactProducer(
        identity=identity_id,
        adapter=report.artifacts.runner if report.artifacts else None,
        provider=(agent.metadata_json or {}).get("llm_provider"),
    )
    changed_files = []
    key_decisions = []
    if report.artifacts:
        changed_files = report.artifacts.changed_files or report.artifacts.scope_diff or []
        key_decisions = report.artifacts.key_decisions or []

    artifacts = [
        _code_patch_artifact(task_id=task.task_id, run_id=run.run_id, producer=producer, changed_files=changed_files),
        _changed_file_artifact(task_id=task.task_id, run_id=run.run_id, producer=producer, changed_files=changed_files),
        _test_report_artifact(task_id=task.task_id, run_id=run.run_id, producer=producer, report=report),
        _review_artifact(task_id=task.task_id, run_id=run.run_id, producer=producer, decisions=key_decisions),
        _pr_artifact(task_id=task.task_id, run_id=run.run_id, producer=producer, pr_url=report.pr_url),
    ]
    saved_artifacts: list[Artifact] = []
    store = _artifact_store()
    for artifact in [a for a in artifacts if a is not None]:
        saved_artifacts.append(store.save(artifact))

    claimed_state = "done" if report.status == "done" else "failed"
    if effective_status in ("needs_review", "blocked"):
        claimed_state = "blocked"
    claim = StateClaim(
        task_id=task.task_id,
        run_id=run.run_id,
        producer=identity_id,
        claimed_state=claimed_state,
        message=report.summary,
    )
    _append_jsonl("state_claims", claim)

    events = [
        append_event("agent.started", task_id=task.task_id, run_id=run.run_id, producer=identity_id, message="Run recorded"),
        append_event("state.claimed", task_id=task.task_id, run_id=run.run_id, producer=identity_id, message=claim.message, payload={"claimed_state": claim.claimed_state}),
    ]
    for artifact in saved_artifacts:
        events.append(
            append_event(
                "artifact.produced",
                task_id=task.task_id,
                run_id=run.run_id,
                producer=identity_id,
                message=artifact.title,
                payload={"artifact_id": artifact.artifact_id, "artifact_type": artifact.type},
            )
        )
        if artifact.status == "verified":
            events.append(
                append_event(
                    "artifact.verified",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    producer="dipeen://verifier",
                    message=artifact.title,
                    payload={"artifact_id": artifact.artifact_id},
                )
            )

    reconciled = record_task_state(task, event_type="state.reconciled")
    events.append(reconciled)

    memory_candidates: list[MemoryCandidate] = []
    review_artifact = next((a for a in saved_artifacts if a.type == "review_result"), None)
    for decision in key_decisions:
        candidate = MemoryCandidate(
            source_artifact_id=review_artifact.artifact_id if review_artifact else None,
            memory_type="project_decision",
            proposed_content=decision,
            confidence=0.68,
        )
        _append_jsonl("memory_candidates", candidate)
        memory_candidates.append(candidate)
        events.append(
            append_event(
                "memory.candidate_created",
                task_id=task.task_id,
                run_id=run.run_id,
                producer=identity_id,
                message=decision,
                payload={"memory_candidate_id": candidate.memory_candidate_id},
            )
        )

    if gatekeeper_info and gatekeeper_info.get("verdict") == "needs_human":
        permission = PermissionRequest(
            task_id=task.task_id,
            run_id=run.run_id,
            requester=identity_id,
            action="workspace.write",
            target=task.branch,
            reason=gatekeeper_info.get("reason") or "Gatekeeper requires human review",
            risk="high",
            requires_human_approval=True,
        )
        permission.policy_decision = policy.classify(permission.action)
        _permission_ledger().save(permission)              # canonical store(JSONL 폐기)
        events.append(
            append_event(
                "permission.requested",
                task_id=task.task_id,
                run_id=run.run_id,
                producer=identity_id,
                message=permission.reason,
                payload={"permission_request_id": permission.permission_request_id},
            )
        )

    return {
        "run": run,
        "events": events,
        "artifacts": saved_artifacts,
        "state_claim": claim,
        "memory_candidates": memory_candidates,
    }


def list_runs(*, task_id: str | None = None, limit: int = 100) -> list[Run]:
    runs: list[Run] = []
    root = control_plane_root() / "runs"
    if root.exists():
        for path in sorted(root.glob("R-*.json")):
            try:
                run = Run.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if task_id and run.task_id != task_id:
                continue
            runs.append(run)
    return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]


def get_run(run_id: str) -> Run | None:
    for run in list_runs(limit=10000):
        if run.run_id == run_id:
            return run
    return None


def list_events(*, task_id: str | None = None, run_id: str | None = None, tail: int = 100) -> list[Event]:
    events = _event_log().read_all()
    if task_id:
        events = [e for e in events if e.task_id == task_id]
    if run_id:
        events = [e for e in events if e.run_id == run_id]
    return events[-tail:]


def list_artifacts(*, task_id: str | None = None, run_id: str | None = None, type: str | None = None) -> list[Artifact]:
    artifacts = _artifact_store().list(task_id=task_id)
    if run_id:
        artifacts = [a for a in artifacts if a.run_id == run_id]
    if type:
        artifacts = [a for a in artifacts if a.type == type]
    return sorted(artifacts, key=lambda a: a.created_at, reverse=True)


def get_artifact(artifact_id: str) -> Artifact | None:
    return _artifact_store().load(artifact_id)


def list_state_claims(*, task_id: str | None = None, run_id: str | None = None) -> list[StateClaim]:
    claims = _read_jsonl("state_claims", StateClaim)
    if task_id:
        claims = [c for c in claims if c.task_id == task_id]
    if run_id:
        claims = [c for c in claims if c.run_id == run_id]
    return sorted(claims, key=lambda c: c.created_at, reverse=True)


def list_permissions(*, status: str | None = None) -> list[PermissionRequest]:
    items = _permission_ledger().all()                 # canonical = PermissionLedger
    if status:
        items = [p for p in items if p.state == status]
    return items


def approve_permission(permission_request_id: str, *, decided_by: str = "user://web") -> dict:
    """승인 → canonical ledger 갱신 + (side-effect action이면) permission.execute command 생성.
    **Core는 실행하지 않는다** — command만. dry_run/manual_handoff/local_execute는 worker가 결정."""
    command = permission_nat.approve(permission_request_id, decider=decided_by,
                                     ledger=_permission_ledger(), queue=_command_queue())
    return {"permission": _permission_ledger().get(permission_request_id), "command": command}


def reject_permission(permission_request_id: str, *, decided_by: str = "user://web") -> PermissionRequest | None:
    return permission_nat.reject(permission_request_id, ledger=_permission_ledger(),
                                 reason=f"rejected by {decided_by}")


def list_memory_candidates(*, status: str | None = None) -> list[dict[str, Any]]:
    items = _read_jsonl("memory_candidates", MemoryCandidate)
    out: list[dict[str, Any]] = []
    for item in items:
        data = item.model_dump(mode="json")
        data["status"] = "pending"
        out.append(data)
    if status and status != "pending":
        return []
    return out


def update_memory_candidate(memory_candidate_id: str, status: str) -> dict[str, Any] | None:
    items = _read_jsonl("memory_candidates", MemoryCandidate)
    target = None
    for item in items:
        if item.memory_candidate_id == memory_candidate_id:
            target = item
            append_event(
                "memory.promoted" if status == "promoted" else "memory.rejected",
                producer="dipeen://memory",
                message=item.proposed_content,
                payload={"memory_candidate_id": item.memory_candidate_id, "status": status},
            )
            break
    if not target:
        return None
    if status == "promoted":
        promoted_dir = control_plane_root() / "memory" / "promoted"
        promoted_dir.mkdir(parents=True, exist_ok=True)
        (promoted_dir / f"{target.memory_candidate_id}.json").write_text(
            target.model_dump_json(indent=2),
            encoding="utf-8",
        )
    remaining = [item for item in items if item.memory_candidate_id != memory_candidate_id]
    _write_jsonl("memory_candidates", remaining)
    data = target.model_dump(mode="json")
    data["status"] = status
    return data
