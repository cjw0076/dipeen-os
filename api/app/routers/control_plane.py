"""Canonical Dipeen control-plane API.

These endpoints expose Dipeen-owned truth to the Web UI. Provider runtimes can
still be noisy or provider-specific; this API returns normalized runs, events,
artifacts, permissions, memory candidates, and aggregate state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, DecisionCard, Task
from app.nat.contracts import Message, MessageLink, Room, SenderRef
from app.nat.executors import default_executor_mode
from app.db.session import get_db
from app.routers.auth import get_team_id
from app.routers.events import broadcast
from app.services import control_plane

router = APIRouter()


class RoomCreateBody(BaseModel):
    room_id: str
    room_type: Literal["general", "goal", "task", "run", "permission", "memory", "discussion"] = "general"
    ref_id: str | None = None
    title: str = ""


class MessagePostBody(BaseModel):
    sender_type: Literal["human", "agent", "system"] = "human"
    sender_id: str = "user://web"
    message_type: Literal["discussion.message", "decision.proposal", "command.proposal", "system"] = "discussion.message"
    body: str
    links: list[dict[str, str]] = Field(default_factory=list)


class AssignmentBody(BaseModel):
    role: str | None = None                # frontend | backend | qa | integrator | memory
    user: str | None = None                # 사람
    repo: str | None = None                # repo slug
    preferred_worker: str | None = None    # 특정 머신
    provider: str | None = None            # provider 오버라이드


class ProposalCreateBody(BaseModel):
    room_id: str
    intent: str
    provider: str = "claude"
    workspace_root: str = ""
    proposed_by: str = "user://web"
    message_id: str | None = None
    acceptance: list[dict[str, Any]] = Field(default_factory=list)
    assignment: AssignmentBody | None = None   # 배정 → required_capabilities 라우팅


class PlanStepBody(BaseModel):
    intent: str
    provider: str = "claude"
    workspace_root: str = ""
    acceptance: list[dict[str, Any]] = Field(default_factory=list)
    assignment: AssignmentBody | None = None


class PlanProposalBody(BaseModel):
    room_id: str
    proposed_by: str = "agent://team/pm"
    plan: list[PlanStepBody]


class ProposalDecisionBody(BaseModel):
    decided_by: str = "user://web"


class RoutingPreviewBody(BaseModel):
    assignment: AssignmentBody | None = None
    provider: str = "claude"


class ActionCandidateApproveBody(BaseModel):
    room_id: str
    candidate: dict[str, Any]                    # ActionCandidate(회의 정리물에서 나온 후보)
    proposed_by: str = "user://web"


class WorkerRegisterBody(BaseModel):
    worker_id: str
    capabilities: list[str] = Field(default_factory=lambda: ["provider.claude", "workspace.write"])
    workspaces: list[dict[str, Any]] = Field(default_factory=list)   # WorkerWorkspace[] (local_path는 worker-local)


class WorkerPollBody(BaseModel):
    capabilities: list[str] = Field(default_factory=list)


class WorkerResultBody(BaseModel):
    status: str = "done"
    summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    tests_passed: bool = False
    pr_url: str | None = None
    key_decisions: list[str] = Field(default_factory=list)
    runner: str | None = None


class PermissionResultBody(BaseModel):
    artifact: dict[str, Any]                     # worker가 만든 receipt artifact(would_execute/실행 증거)
    permission_id: str | None = None
    executed: bool = False                       # dry_run/handoff=False, 실제 실행=True


class ProbeResultBody(BaseModel):
    provider: str                                # omo | hermes (어떤 provider를 probe했나)
    exit: int = -1                               # provider CLI exit code
    stdout: str = ""
    stderr: str = ""


def _task_bucket(status: str | None) -> str:
    raw = (status or "").lower()
    if raw in ("done", "completed", "merged"):
        return "done"
    if raw in ("in_progress", "running", "working"):
        return "running"
    if raw in ("blocked", "error", "cancelled", "rejected", "needs_review"):
        return "blocked"
    if raw in ("pending", "ready"):
        return "ready"
    return "waiting"


@router.get("/control-plane/summary")
async def get_control_plane_summary(
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    task_result = await db.execute(select(Task).where(Task.team_id == team_id))
    tasks = task_result.scalars().all()
    agent_result = await db.execute(select(Agent).where(Agent.team_id == team_id))
    agents = agent_result.scalars().all()
    decision_result = await db.execute(
        select(DecisionCard).where(DecisionCard.team_id == team_id, DecisionCard.status == "pending")
    )
    decisions = decision_result.scalars().all()

    counts = {"total": len(tasks), "done": 0, "running": 0, "ready": 0, "waiting": 0, "blocked": 0}
    for task in tasks:
        counts[_task_bucket(task.status)] += 1

    runs = control_plane.list_runs(limit=12)
    events = control_plane.list_events(tail=40)
    artifacts = control_plane.list_artifacts()[:12]
    permissions = control_plane.list_permissions(status="requested")
    memory_candidates = control_plane.list_memory_candidates(status="pending")
    proposals = control_plane.list_proposals(state="proposed")
    workers = control_plane.list_workers()
    queued_commands = control_plane.list_commands(state="queued")

    providers = []
    for agent in agents:
        meta = agent.metadata_json or {}
        provider = meta.get("llm_provider") or meta.get("provider") or "unknown"
        model = meta.get("model") or "unknown"
        providers.append({
            "id": agent.agent_id,
            "label": agent.agent_id,
            "provider": provider,
            "model": model,
            "status": agent.status,
            "healthy": agent.status not in ("offline", "error", "failed"),
            "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        })

    system_health = [
        {"id": "dipeen-core", "label": "Dipeen Core", "status": "healthy", "detail": "API reachable"},
        {"id": "nat-store", "label": "NAT Store", "status": "healthy", "detail": str(control_plane.control_plane_root())},
        {
            "id": "provider-mesh",
            "label": "Provider Mesh",
            "status": "healthy" if any(p["healthy"] for p in providers) else "waiting",
            "detail": f"{sum(1 for p in providers if p['healthy'])}/{len(providers)} providers online",
        },
        {
            "id": "permission-proxy",
            "label": "Permission Proxy",
            "status": "waiting" if permissions else "healthy",
            "detail": f"{len(permissions)} awaiting approval",
        },
        {
            "id": "worker-pool",
            "label": "Worker Pool",
            "status": "healthy" if workers else "waiting",
            "detail": f"{len(workers)} registered, {len(queued_commands)} queued commands",
        },
    ]

    return {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "team_id": team_id,
        "goal_progress": counts,
        "system_health": system_health,
        "active_runs": runs,
        "pending_permissions": permissions,
        "pending_decisions": decisions,
        "latest_events": events,
        "latest_artifacts": artifacts,
        "memory_candidates": memory_candidates,
        "providers": providers,
        "pending_proposals": proposals,
        "workers": workers,
        "queued_commands": queued_commands,
    }


@router.get("/rooms")
async def list_rooms():
    return control_plane.list_rooms()


@router.post("/rooms")
async def create_room(body: RoomCreateBody):
    room = control_plane.create_room(Room(
        room_id=body.room_id,
        room_type=body.room_type,
        ref_id=body.ref_id,
        title=body.title,
    ))
    await broadcast({"type": "room.created", "room_id": room.room_id, "room_type": room.room_type})
    return room


@router.get("/rooms/{room_id}")
async def get_room(room_id: str):
    room = control_plane.get_room(room_id)
    if not room:
        raise HTTPException(404, f"Room {room_id} not found")
    return room


@router.get("/rooms/{room_id}/messages")
async def list_room_messages(room_id: str):
    return control_plane.list_messages(room_id)


@router.post("/rooms/{room_id}/messages")
async def post_room_message(room_id: str, body: MessagePostBody):
    message = control_plane.post_message(Message(
        room_id=room_id,
        sender=SenderRef(type=body.sender_type, id=body.sender_id),
        message_type=body.message_type,
        body=body.body,
        links=[MessageLink(target_type=item["target_type"], target_id=item["target_id"]) for item in body.links],
    ))
    await broadcast({
        "type": "message.created",
        "message_id": message.message_id,
        "room_id": room_id,
        "message_type": message.message_type,
    })
    return message


@router.post("/routing/preview")
async def routing_preview(body: RoutingPreviewBody):
    """배정 → '이 작업은 누구에게 가는지' 미리보기(Assignment UI용). User는 capability를 몰라도 됨."""
    return control_plane.preview_routing(
        body.assignment.model_dump() if body.assignment else None, provider=body.provider)


@router.post("/rooms/{room_id}/close")
async def close_meeting(room_id: str):
    """회의 '정리' — 메시지를 decision/task/permission/memory/question 후보로 분류. 승인 전엔 작업 아님."""
    return control_plane.close_meeting(room_id)


@router.post("/meeting/action-candidates/approve")
async def approve_action_candidate(body: ActionCandidateApproveBody):
    """승인된 작업 후보 → CommandProposal(배정 포함). 회의→작업의 유일한 실행 경계(confirm 별도)."""
    proposal = control_plane.approve_action_candidate(
        body.candidate, room_id=body.room_id, proposed_by=body.proposed_by)
    await broadcast({"type": "proposal.created", "proposal_id": proposal.proposal_id,
                     "room_id": proposal.room_id, "state": proposal.state})
    return proposal


@router.get("/proposals")
async def list_proposals(room_id: str | None = Query(None), state: str | None = Query(None)):
    return control_plane.list_proposals(room_id=room_id, state=state)


@router.post("/proposals")
async def create_proposal(body: ProposalCreateBody):
    proposal = control_plane.propose_command(
        room_id=body.room_id,
        intent=body.intent,
        provider=body.provider,
        workspace_root=body.workspace_root,
        proposed_by=body.proposed_by,
        message_id=body.message_id,
        acceptance=body.acceptance,
        assignment=body.assignment.model_dump() if body.assignment else None,
    )
    await broadcast({
        "type": "proposal.created",
        "proposal_id": proposal.proposal_id,
        "room_id": proposal.room_id,
        "state": proposal.state,
    })
    return proposal


@router.post("/proposals/plan")
async def create_plan_proposals(body: PlanProposalBody):
    items = control_plane.propose_plan(
        [step.model_dump() for step in body.plan],
        room_id=body.room_id,
        proposed_by=body.proposed_by,
    )
    await broadcast({"type": "proposal.created", "room_id": body.room_id, "count": len(items)})
    return items


@router.post("/proposals/{proposal_id}/confirm")
async def confirm_proposal(proposal_id: str, body: ProposalDecisionBody):
    command = control_plane.confirm_proposal(proposal_id, decided_by=body.decided_by)
    if not command:
        raise HTTPException(404, f"Proposed command {proposal_id} not found or already decided")
    await broadcast({
        "type": "command.queued",
        "proposal_id": proposal_id,
        "command_id": command.command_id,
        "task_id": command.task_id,
        "run_id": command.run_id,
    })
    return command


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, body: ProposalDecisionBody):
    proposal = control_plane.reject_proposal(proposal_id, decided_by=body.decided_by)
    if not proposal:
        raise HTTPException(404, f"Proposed command {proposal_id} not found")
    await broadcast({"type": "proposal.rejected", "proposal_id": proposal_id})
    return proposal


@router.get("/workers")
async def list_workers():
    return control_plane.list_workers()


@router.post("/workers")
async def register_worker(body: WorkerRegisterBody):
    worker = control_plane.register_worker(body.worker_id, body.capabilities, workspaces=body.workspaces)
    await broadcast({"type": "worker.updated", "worker_id": worker.worker_id, "state": worker.state})
    return worker


@router.post("/workers/{worker_id}/heartbeat")
async def heartbeat_worker(worker_id: str):
    worker = control_plane.heartbeat_worker(worker_id)
    if not worker:
        raise HTTPException(404, f"Worker {worker_id} not found")
    await broadcast({"type": "worker.updated", "worker_id": worker.worker_id, "state": worker.state})
    return worker


@router.get("/commands")
async def list_commands(state: str | None = Query(None)):
    return control_plane.list_commands(state=state)


@router.post("/workers/{worker_id}/commands/poll")
async def poll_worker_command(worker_id: str, body: WorkerPollBody):
    worker = control_plane.heartbeat_worker(worker_id)
    if not worker:
        raise HTTPException(404, f"Worker {worker_id} not found")
    command = control_plane.poll_worker_command(worker_id, body.capabilities or worker.capabilities)
    if not command:
        return {"command": None}
    await broadcast({
        "type": "command.leased",
        "worker_id": worker_id,
        "command_id": command.command_id,
        "task_id": command.task_id,
        "run_id": command.run_id,
    })
    return {"command": command}


@router.post("/workers/{worker_id}/commands/{command_id}/ack")
async def ack_worker_command(worker_id: str, command_id: str):
    command = control_plane.ack_worker_command(worker_id, command_id)
    if not command:
        raise HTTPException(404, f"Command {command_id} not found")
    await broadcast({"type": "command.running", "worker_id": worker_id, "command_id": command_id})
    return command


@router.post("/workers/{worker_id}/commands/{command_id}/complete")
async def complete_worker_command(worker_id: str, command_id: str):
    command = control_plane.complete_worker_command(worker_id, command_id)
    if not command:
        raise HTTPException(404, f"Command {command_id} not found or not leased by {worker_id}")
    await broadcast({"type": "command.completed", "worker_id": worker_id, "command_id": command_id})
    return command


@router.post("/workers/{worker_id}/commands/{command_id}/fail")
async def fail_worker_command(worker_id: str, command_id: str):
    command = control_plane.fail_worker_command(worker_id, command_id)
    if not command:
        raise HTTPException(404, f"Command {command_id} not found or not leased by {worker_id}")
    await broadcast({"type": "command.failed", "worker_id": worker_id, "command_id": command_id})
    return command


@router.post("/workers/{worker_id}/commands/{command_id}/result")
async def ingest_worker_result(worker_id: str, command_id: str, body: WorkerResultBody):
    payload = control_plane.ingest_worker_command_result(
        worker_id=worker_id,
        command_id=command_id,
        status=body.status,
        summary=body.summary,
        changed_files=body.changed_files,
        tests_passed=body.tests_passed,
        pr_url=body.pr_url,
        key_decisions=body.key_decisions,
        runner=body.runner,
    )
    if not payload:
        raise HTTPException(404, f"Command {command_id} not found or not leased by {worker_id}")
    command = payload["command"]
    result = payload["result"]
    await broadcast({
        "type": "run.updated",
        "worker_id": worker_id,
        "command_id": command_id,
        "task_id": command.task_id,
        "run_id": command.run_id,
        "status": result.state,
    })
    await broadcast({
        "type": "event.created",
        "task_id": command.task_id,
        "run_id": command.run_id,
        "event_type": "state.reconciled",
    })
    return {"command": command, "state": result.state, "failure_type": result.failure_type, "reasons": result.reasons}


@router.post("/workers/{worker_id}/commands/{command_id}/permission-result")
async def ingest_worker_permission_result(worker_id: str, command_id: str, body: PermissionResultBody):
    """승인된 permission.execute를 worker가 처리해 올린 receipt를 영속·reconcile. Core는 실행 안 함."""
    payload = control_plane.ingest_permission_result(
        worker_id=worker_id,
        command_id=command_id,
        artifact=body.artifact,
        permission_id=body.permission_id,
        executed=body.executed,
    )
    if not payload:
        raise HTTPException(404, f"Command {command_id} not found or not leased by {worker_id}")
    command = payload["command"]
    await broadcast({
        "type": "permission.executed",
        "worker_id": worker_id,
        "command_id": command_id,
        "task_id": command.task_id,
        "run_id": command.run_id,
        "executed": payload["executed"],
        "artifact_id": payload["artifact_id"],
    })
    await broadcast({
        "type": "run.updated",
        "worker_id": worker_id,
        "command_id": command_id,
        "task_id": command.task_id,
        "run_id": command.run_id,
        "status": payload.get("state"),
    })
    return payload


@router.post("/workers/{worker_id}/commands/{command_id}/probe-result")
async def ingest_worker_probe_result(worker_id: str, command_id: str, body: ProbeResultBody):
    """worker가 provider read-only probe(doctor/status)를 실행해 올린 결과를 task-less Event로 수집. Core 실행 0."""
    payload = control_plane.ingest_probe_result(
        worker_id=worker_id, command_id=command_id,
        probe={"provider": body.provider, "exit": body.exit, "stdout": body.stdout, "stderr": body.stderr})
    if not payload:
        raise HTTPException(404, f"Command {command_id} not found or not leased by {worker_id}")
    await broadcast({
        "type": "provider.probed",
        "worker_id": worker_id,
        "command_id": command_id,
        "provider": payload["provider"],
    })
    return payload


@router.get("/runs")
async def list_runs(
    task_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    return control_plane.list_runs(task_id=task_id, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = control_plane.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


@router.get("/events")
async def list_events(
    task_id: str | None = Query(None),
    run_id: str | None = Query(None),
    tail: int = Query(100, ge=1, le=500),
):
    return control_plane.list_events(task_id=task_id, run_id=run_id, tail=tail)


@router.get("/artifacts")
async def list_artifacts(
    task_id: str | None = Query(None),
    run_id: str | None = Query(None),
    type: str | None = Query(None),
):
    return control_plane.list_artifacts(task_id=task_id, run_id=run_id, type=type)


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    artifact = control_plane.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(404, f"Artifact {artifact_id} not found")
    return artifact


@router.get("/state-claims")
async def list_state_claims(
    task_id: str | None = Query(None),
    run_id: str | None = Query(None),
):
    return control_plane.list_state_claims(task_id=task_id, run_id=run_id)


@router.get("/permissions")
async def list_permissions(status: str | None = Query(None)):
    return control_plane.list_permissions(status=status)


@router.post("/permissions/{permission_request_id}/approve")
async def approve_permission(permission_request_id: str):
    """승인 → canonical ledger + (side-effect면) permission.execute command. Core는 실행 안 함."""
    result = control_plane.approve_permission(permission_request_id)
    permission = result["permission"]
    if not permission:
        raise HTTPException(404, f"Permission {permission_request_id} not found")
    command = result["command"]
    await broadcast({
        "type": "permission.updated",
        "permission_request_id": permission.permission_request_id,
        "status": permission.state,
        "task_id": permission.task_id,
        "run_id": permission.run_id,
    })
    if command:
        await broadcast({"type": "command.queued", "command_id": command.command_id,
                         "task_id": command.task_id, "run_id": command.run_id})
    return {
        "permission_id": permission.permission_request_id,
        "status": permission.state,
        "executor_mode": default_executor_mode(),
        "command_id": command.command_id if command else None,
        "message": ("Permission approved; execute command queued for worker."
                    if command else "Permission approved."),
    }


@router.post("/permissions/{permission_request_id}/reject")
async def reject_permission(permission_request_id: str):
    permission = control_plane.reject_permission(permission_request_id)
    if not permission:
        raise HTTPException(404, f"Permission {permission_request_id} not found")
    await broadcast({
        "type": "permission.updated",
        "permission_request_id": permission.permission_request_id,
        "status": permission.state,
        "task_id": permission.task_id,
        "run_id": permission.run_id,
    })
    return permission


@router.get("/memory-candidates")
async def list_memory_candidates(status: str | None = Query(None)):
    return control_plane.list_memory_candidates(status=status)


@router.post("/memory-candidates/{memory_candidate_id}/promote")
async def promote_memory_candidate(memory_candidate_id: str):
    candidate = control_plane.update_memory_candidate(memory_candidate_id, "promoted")
    if not candidate:
        raise HTTPException(404, f"Memory candidate {memory_candidate_id} not found")
    await broadcast({"type": "memory.candidate_updated", "memory_candidate_id": memory_candidate_id, "status": "promoted"})
    return candidate


@router.post("/memory-candidates/{memory_candidate_id}/reject")
async def reject_memory_candidate(memory_candidate_id: str):
    candidate = control_plane.update_memory_candidate(memory_candidate_id, "rejected")
    if not candidate:
        raise HTTPException(404, f"Memory candidate {memory_candidate_id} not found")
    await broadcast({"type": "memory.candidate_updated", "memory_candidate_id": memory_candidate_id, "status": "rejected"})
    return candidate
