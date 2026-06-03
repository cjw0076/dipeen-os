import asyncio
import hashlib
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Agent, Task, AgentMessage, UsageLog
from app.db.session import get_db
from app.schemas.agent import (
    AgentRegister, AgentHeartbeat, AgentReport, AgentOut,
    AgentCapabilityUpdate, AgentMessageCreate, RosterEntry,
)
from app.routers.events import broadcast
from app.routers.auth import get_team_id, require_owner
from app.services.manifest import update_agents_manifest
from app.services import control_plane

async def _legacy_deprecation(response: Response) -> None:
    """M10.5 strangler — 레거시 /api/agents(poll/report 직접 경로)에 deprecation 신호를 단다.

    **비파괴**: 기능은 유지(구 agent-client 경로 비교 가능)하되, 모든 응답이 canonical 경로로
    이전하라고 알린다. canonical = control_plane command queue + worker HTTP protocol.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Warning"] = (
        '299 - "Legacy /api/agents poll/report is deprecated; '
        'use /api/control-plane/* and the worker HTTP protocol (/api/workers)."'
    )
    response.headers["Link"] = '</api/control-plane/summary>; rel="successor-version"'


# 레거시 경로 — canonical(control_plane)로 단일화 진행 중. deprecation 헤더는 비파괴(기능 유지).
router = APIRouter(dependencies=[Depends(_legacy_deprecation)])


# ── 등록 / 목록 ────────────────────────────────────────────────────

@router.post("", response_model=AgentOut, status_code=201)
async def register_agent(
    body: AgentRegister,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """에이전트 등록 (최초 1회 또는 재등록)"""
    stmt = select(Agent).where(
        Agent.team_id == team_id,
        Agent.agent_id == body.agent_id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if agent:
        agent.role = body.role or agent.role
        if body.metadata:
            agent.metadata_json = {**(agent.metadata_json or {}), **body.metadata}
        agent.status = "idle"
        agent.last_heartbeat = datetime.now(timezone.utc)
    else:
        agent = Agent(
            team_id=team_id,
            agent_id=body.agent_id,
            role=body.role,
            status="idle",
            metadata_json=body.metadata or {},
            last_heartbeat=datetime.now(timezone.utc),
        )
        db.add(agent)

    await db.commit()
    await db.refresh(agent)

    await broadcast({
        "type": "agent_status",
        "agent_id": agent.agent_id,
        "status": agent.status,
        "current_task_id": agent.current_task_id,
    })

    # M-2: DIPEEN_AGENTS.md 자동 갱신 (best-effort)
    await update_agents_manifest(db, team_id)

    return agent


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(Agent).where(Agent.team_id == team_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/search/by-role")
async def search_agents_by_role(
    role: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(Agent).where(Agent.team_id == team_id)
    if role:
        stmt = stmt.where(Agent.role.ilike(f"%{role}%"))
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await db.execute(stmt)
    agents = result.scalars().all()
    return [
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "status": a.status,
            "current_task_id": a.current_task_id,
            "metadata": a.metadata_json,
        }
        for a in agents
    ]


# ── C-3: Team Roster ──────────────────────────────────────────────

@router.get("/roster", response_model=dict)
async def get_roster(
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """전체 에이전트 역량 스냅샷 — PM loop가 태스크 배분 전 호출"""
    stmt = select(Agent).where(Agent.team_id == team_id)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    roster = []
    for a in agents:
        meta = a.metadata_json or {}
        roster.append({
            "agent_id": a.agent_id,
            "role": a.role,
            "status": a.status,
            "current_task_id": a.current_task_id,
            "available": a.status == "idle" and a.current_task_id is None,
            "skills": meta.get("skills", []),
            "mcps": meta.get("mcps", []),
            "competency": meta.get("competency", {}),
            "model": meta.get("model", "unknown"),
            "max_concurrent": meta.get("max_concurrent", 1),
            "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
            "llm_provider": meta.get("llm_provider", "anthropic"),
            "personas": meta.get("personas", []),
        })

    return {
        "agents": roster,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 단일 에이전트 ─────────────────────────────────────────────────

@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    return await _get_agent(agent_id, db, team_id)


# ── 에이전트 삭제 ─────────────────────────────────────────────────

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
    _: None = Depends(require_owner),
):
    """에이전트 DB 삭제 (Settings에서 수동 제거)"""
    agent = await _get_agent(agent_id, db, team_id)
    await db.delete(agent)
    await db.commit()
    await broadcast({
        "type": "agent_status",
        "agent_id": agent_id,
        "status": "removed",
        "current_task_id": None,
    })
    return {"ok": True, "agent_id": agent_id}


# ── C-1: Capability 등록 ──────────────────────────────────────────

@router.patch("/{agent_id}/capability")
async def update_capability(
    agent_id: str,
    body: AgentCapabilityUpdate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """C-1: agent-client 시작 시 로컬 환경(MCP/skills) 스캔 결과 등록"""
    agent = await _get_agent(agent_id, db, team_id)
    meta = dict(agent.metadata_json or {})

    if body.skills:
        meta["skills"] = body.skills
    if body.mcps:
        meta["mcps"] = body.mcps
    if body.model:
        meta["model"] = body.model
    meta["max_concurrent"] = body.max_concurrent
    if body.llm_provider:
        meta["llm_provider"] = body.llm_provider
    if body.personas:
        meta["personas"] = body.personas

    # profile_hash: skills+mcps+model+personas의 MD5 (캐시 무효화용)
    profile_str = json.dumps({
        "skills": sorted(meta.get("skills", [])),
        "mcps": sorted(meta.get("mcps", [])),
        "model": meta.get("model", ""),
        "llm_provider": meta.get("llm_provider", ""),
        "personas": sorted(meta.get("personas", [])),
    }, sort_keys=True)
    meta["profile_hash"] = hashlib.md5(profile_str.encode()).hexdigest()[:8]

    agent.metadata_json = meta
    await db.commit()

    await broadcast({
        "type": "agent_status",
        "agent_id": agent.agent_id,
        "status": agent.status,
        "current_task_id": agent.current_task_id,
        "skills": meta.get("skills", []),
        "competency": meta.get("competency", {}),
    })
    return {"ok": True, "profile_hash": meta["profile_hash"]}


# ── Heartbeat ─────────────────────────────────────────────────────

@router.post("/{agent_id}/heartbeat", response_model=AgentOut)
async def heartbeat(
    agent_id: str,
    body: AgentHeartbeat,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    agent = await _get_agent(agent_id, db, team_id)
    agent.status = body.status
    agent.current_task_id = body.current_task_id
    agent.last_heartbeat = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)

    await broadcast({
        "type": "agent_status",
        "agent_id": agent.agent_id,
        "status": agent.status,
        "current_task_id": agent.current_task_id,
    })
    return agent


# ── C-2: 역량 기반 Poll ────────────────────────────────────────────

@router.get("/{agent_id}/poll")
async def poll_task(
    agent_id: str,
    room_id: str = "general",          # K-1: 채팅방 ID (에이전트가 보고할 채팅방)
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """C-2: role + skills 매칭 후 pending 태스크를 가져옴. 없으면 poll_timeout 초 대기."""
    agent = await _get_agent(agent_id, db, team_id)
    agent_role = (agent.role or "").upper()
    # F-3: 토큰 쿼터 체크 — 예산 초과 시 태스크 배정 거부
    if agent.monthly_token_budget is not None and agent.tokens_used_this_month >= agent.monthly_token_budget:
        print(f"[poll] {agent_id} 토큰 쿼터 초과 ({agent.tokens_used_this_month}/{agent.monthly_token_budget})", flush=True)
        return {"task_id": None, "reason": "token_quota_exceeded"}

    meta = agent.metadata_json or {}
    agent_skills = set(meta.get("skills", []))
    agent_personas = set(meta.get("personas", []))
    agent_competency = float(meta.get("competency", {}).get(agent_role, 0))

    # role 약어 매핑 (FE↔Frontend Engineer, BE↔Backend Engineer, QA↔QA Engineer)
    _ROLE_ALIASES: dict[str, list[str]] = {
        "FE": ["FE", "FRONTEND ENGINEER", "FRONTEND", "FE ENGINEER"],
        "BE": ["BE", "BACKEND ENGINEER", "BACKEND", "BE ENGINEER"],
        "QA": ["QA", "QA ENGINEER", "QUALITY ASSURANCE"],
        "PM": ["PM", "PM ENGINEER", "PROJECT MANAGER", "PRODUCT MANAGER"],
    }
    role_variants = {agent_role}
    for canonical, aliases in _ROLE_ALIASES.items():
        if agent_role in [a.upper() for a in aliases]:
            role_variants.update(a.upper() for a in aliases)

    # S-1: 5분 이상 in_progress인 태스크 자동 error 전환 (agent crash 대비)
    _TASK_TIMEOUT = timedelta(minutes=5)
    stale_cutoff = datetime.now(timezone.utc) - _TASK_TIMEOUT
    stale_stmt = select(Task).where(
        Task.team_id == team_id,
        Task.status == "in_progress",
        Task.updated_at < stale_cutoff,
    )
    stale_result = await db.execute(stale_stmt)
    stale_tasks = stale_result.scalars().all()
    for stale in stale_tasks:
        stale.status = "error"
        stale.result = {"error": "agent_timeout", "message": "Task timed out (5min without update)"}
        stale.completed_at = datetime.now(timezone.utc)
        stale.updated_at = datetime.now(timezone.utc)
        # 해당 에이전트의 current_task_id 리셋
        if stale.assigned_agent_id:
            stale_agent_stmt = select(Agent).where(
                Agent.id == stale.assigned_agent_id,
                Agent.team_id == team_id,
            )
            stale_agent_result = await db.execute(stale_agent_stmt)
            stale_agent = stale_agent_result.scalar_one_or_none()
            if stale_agent:
                stale_agent.current_task_id = None
                stale_agent.status = "idle"
        await db.commit()
        await broadcast({
            "type": "task_update",
            "task_id": stale.task_id,
            "status": "error",
            "error": "agent_timeout",
        })
        print(f"[poll] Task {stale.task_id} timed out → error", flush=True)

    for _ in range(settings.poll_timeout):
        # 1단계: role 매칭 (required_role ∈ agent role variants OR required_role IS NULL)
        stmt = (
            select(Task)
            .where(
                Task.team_id == team_id,
                Task.status == "pending",
                Task.blocked_by == None,
                or_(
                    Task.required_role.in_(role_variants),
                    Task.required_role == None,
                ),
            )
            .order_by(Task.created_at.asc())
        )
        result = await db.execute(stmt)
        candidates = result.scalars().all()

        # 2단계: skills + persona 기반 best-match 스코어링 (F-4)
        # persona 매칭: +10 / skill 완전 충족: +5 / competency: +0~1
        matched_task = None
        best_score = -1
        for task in candidates:
            needed = set(task.required_skills or [])
            # skills가 선언된 에이전트만 체크; 빈 skills는 범용(all-accept) 에이전트
            if needed and agent_skills and not needed.issubset(agent_skills):
                continue  # skills 불충족 제외
            score = 5.0  # skills 통과 기본점
            if task.required_persona and task.required_persona in agent_personas:
                score += 10.0
            score += agent_competency / 100.0
            if score > best_score:
                best_score = score
                matched_task = task

        if matched_task:
            matched_task.status = "in_progress"
            matched_task.assigned_agent_id = agent.id
            matched_task.updated_at = datetime.now(timezone.utc)

            agent.status = "working"
            agent.current_task_id = matched_task.task_id
            agent.last_heartbeat = datetime.now(timezone.utc)
            await db.commit()

            await broadcast({
                "type": "agent_status",
                "agent_id": agent.agent_id,
                "status": "working",
                "current_task_id": matched_task.task_id,
            })
            await broadcast({
                "type": "task_update",
                "task_id": matched_task.task_id,
                "status": "in_progress",
                "agent_id": agent.agent_id,
            })

            return {
                "task_id": matched_task.task_id,
                "subject": matched_task.subject,
                "prompt": matched_task.prompt,
                "branch": matched_task.branch,
                "complexity": matched_task.complexity,
                "required_role": matched_task.required_role,
                "required_skills": matched_task.required_skills or [],
                "required_persona": matched_task.required_persona,  # F-4
                "llm_provider": meta.get("llm_provider", "anthropic"),  # F-4
                "room_id": room_id,                                  # K-1
            }

        await asyncio.sleep(1)

    return {"task_id": None}


# ── Report + C-6 competency 진화 ──────────────────────────────────

@router.post("/{agent_id}/report")
async def report(
    agent_id: str,
    body: AgentReport,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """태스크 완료/에러/취소 보고 + C-6 competencyScore 자동 갱신"""
    agent = await _get_agent(agent_id, db, team_id)

    stmt = select(Task).where(Task.task_id == body.task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, f"Task {body.task_id} not found")

    # W1: HQ 출구 게이트 — runner의 "done" 자기보고를 신뢰하지 않고 HQ가 판정한다(truth는 HQ만).
    # completion_promise=None·빈 scope_diff 같은 false-done을 PROMISE_FALSE로 차단 → "done" 대신 rejected.
    effective_status = body.status
    gatekeeper_info = None
    if body.status == "done" and body.artifacts is not None:
        from app.services.gatekeeper import gatekeep
        from app.services.scope_policy import default_scope_claims
        from app.schemas.runner import TaskEnvelope, RunReport
        art = body.artifacts
        _scope = (art.scope_diff or []) if hasattr(art, "scope_diff") else []
        envelope = TaskEnvelope(
            task_id=task.task_id, team_id=team_id,
            subject=task.subject or "", prompt=(task.prompt or ""),
            completion_promise="DONE",
            scope_claims=default_scope_claims(None),
        )
        run_report = RunReport(
            task_id=task.task_id, agent_id=agent_id, runner="claude-code", status="done",
            completion_promise=getattr(art, "completion_promise", None),
            changed_files=_scope, scope_diff=_scope, blockers=[],
        )
        verdict = gatekeep(envelope, run_report, getattr(art, "checks", None) or {})
        gatekeeper_info = {
            "verdict": verdict.verdict, "failure_code": verdict.failure_code,
            "reason": verdict.reason, "scope_violations": verdict.scope_violations,
        }
        if verdict.verdict == "reject":
            effective_status = "rejected"
        elif verdict.verdict == "needs_human":
            effective_status = "needs_review"
        if effective_status != "done":
            print(f"[gate] {task.task_id} runner=done → HQ={effective_status} "
                  f"({verdict.failure_code}: {verdict.reason})", flush=True)

    task.status = effective_status
    task.pr_url = body.pr_url
    task.result = {
        "tests_passed": body.tests_passed,
        "summary": body.summary,
        "usage": body.usage or {},
        "artifacts": body.artifacts.model_dump() if body.artifacts else {},
        "gatekeeper": gatekeeper_info,
    }
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)

    # D-1: UsageLog 저장
    usage = body.usage or {}
    token_count = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
    if token_count > 0:
        usage_log = UsageLog(
            team_id=team_id,
            task_id=task.id,
            agent_id=agent.id,
            token_count=token_count,
            model=usage.get("model") or (agent.metadata_json or {}).get("model"),
            duration_ms=usage.get("duration_ms"),
        )
        db.add(usage_log)
        # F-3: 에이전트 토큰 쿼터 누적
        agent.tokens_used_this_month = (agent.tokens_used_this_month or 0) + token_count

    # blockedBy 자동 해제 — tasks.py와 동일한 단일 경로(_unblock_dependents)를 사용.
    # (과거 이 경로는 status=="pending"으로 필터해 blocked 의존 태스크를 영원히
    #  놓쳤다. 로직을 한 곳으로 모아 두 경로가 다시 갈라지지 않게 한다.)
    if effective_status == "done":
        from app.routers.tasks import _unblock_dependents
        await _unblock_dependents(db, task.task_id)

    # C-6: competencyScore 진화
    updated_competency = {}
    if effective_status == "done":
        meta = dict(agent.metadata_json or {})
        competency = dict(meta.get("competency", {}))
        role = (agent.role or "").upper()

        complexity_bonus = {"trivial": 1, "normal": 3, "complex": 7}.get(
            task.complexity or "normal", 3
        )
        old_score = float(competency.get(role, 0))
        gain = complexity_bonus * (1 - old_score / 100) * 0.5
        competency[role] = round(min(100.0, old_score + gain), 1)

        meta["competency"] = competency
        agent.metadata_json = meta
        updated_competency = competency

    agent.status = "idle"
    agent.current_task_id = None
    agent.last_heartbeat = datetime.now(timezone.utc)
    await db.commit()

    canonical = control_plane.record_agent_report(
        agent=agent,
        task=task,
        report=body,
        effective_status=effective_status,
        gatekeeper_info=gatekeeper_info,
    )
    await broadcast({
        "type": "run.updated",
        "run_id": canonical["run"].run_id,
        "task_id": body.task_id,
        "status": canonical["run"].state,
        "agent_id": agent.agent_id,
    })
    for event in canonical["events"]:
        await broadcast({
            "type": "event.created",
            "event_id": event.event_id,
            "event_type": event.event_type,
            "task_id": event.task_id,
            "run_id": event.run_id,
        })
    for artifact in canonical["artifacts"]:
        await broadcast({
            "type": "artifact.created",
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.type,
            "task_id": artifact.task_id,
            "run_id": artifact.run_id,
            "status": artifact.status,
        })
    await broadcast({
        "type": "state.claimed",
        "task_id": canonical["state_claim"].task_id,
        "run_id": canonical["state_claim"].run_id,
        "claimed_state": canonical["state_claim"].claimed_state,
    })
    for memory_candidate in canonical["memory_candidates"]:
        await broadcast({
            "type": "memory.candidate_created",
            "memory_candidate_id": memory_candidate.memory_candidate_id,
            "task_id": body.task_id,
        })

    await broadcast({
        "type": "task_update",
        "task_id": body.task_id,
        "status": effective_status,
        "pr_url": body.pr_url,
        "failure_code": (gatekeeper_info or {}).get("failure_code", "NONE"),
        "reason": (gatekeeper_info or {}).get("reason"),
    })
    await broadcast({
        "type": "agent_status",
        "agent_id": agent.agent_id,
        "status": "idle",
        "current_task_id": None,
        "competency": updated_competency,
    })
    if token_count > 0:
        await broadcast({
            "type": "usage_update",
            "agent_id": agent.agent_id,
            "task_id": body.task_id,
            "token_count": token_count,
        })
    return {"ok": True, "task_id": body.task_id, "status": body.status}


# ── C-5: A2A 메시지 채널 ──────────────────────────────────────────

@router.post("/{agent_id}/message")
async def send_agent_message(
    agent_id: str,
    body: AgentMessageCreate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """C-5: 에이전트 간 메시지 전송 (질문/정보공유/블로커 보고)"""
    from_agent = await _get_agent(agent_id, db, team_id)

    to_agent_db_id = None
    if body.to_agent_id:
        to_stmt = select(Agent).where(
            Agent.team_id == team_id,
            Agent.agent_id == body.to_agent_id,
        )
        to_result = await db.execute(to_stmt)
        to_agent = to_result.scalar_one_or_none()
        if to_agent:
            to_agent_db_id = to_agent.id

    task_db_id = None
    if body.task_id:
        t_stmt = select(Task).where(Task.task_id == body.task_id)
        t_result = await db.execute(t_stmt)
        t = t_result.scalar_one_or_none()
        if t:
            task_db_id = t.id

    msg = AgentMessage(
        from_agent_id=from_agent.id,
        to_agent_id=to_agent_db_id,
        task_id=task_db_id,
        message_type=body.message_type,
        content=body.content,
        reply_to=body.reply_to,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    await broadcast({
        "type": "agent_message",
        "id": msg.id,
        "from_agent": agent_id,
        "to_agent": body.to_agent_id or "pm",
        "message_type": body.message_type,
        "content": body.content,
        "task_id": body.task_id,
        "reply_to": body.reply_to,
    })
    return {"id": msg.id, "ok": True}


# ── Internal helper ───────────────────────────────────────────────

async def _get_agent(agent_id: str, db: AsyncSession, team_id: str = "default-team") -> Agent:
    stmt = select(Agent).where(
        Agent.team_id == team_id,
        Agent.agent_id == agent_id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent {agent_id} not found")
    return agent
