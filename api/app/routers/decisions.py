"""Decision/Nudge cards.

Agent가 사람의 승인, 선택, 명확화, 위임을 기다릴 때 쓰는 팀 단위 inbox.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DecisionCard
from app.db.session import get_db
from app.routers.auth import get_team_id
from app.routers.events import broadcast
from app.schemas.decision import DecisionAnswer, DecisionCreate, DecisionDelegate, DecisionOut

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_decision_id() -> str:
    return f"D-{uuid.uuid4().hex[:10].upper()}"


def _audit(card: DecisionCard, action: str, by: str = "system", detail: dict | None = None) -> None:
    log = list(card.audit_log or [])
    log.append({
        "action": action,
        "by": by,
        "at": _now().isoformat(),
        **({"detail": detail} if detail else {}),
    })
    card.audit_log = log


async def _get_card(db: AsyncSession, team_id: str, decision_id: str) -> DecisionCard:
    result = await db.execute(
        select(DecisionCard).where(
            DecisionCard.team_id == team_id,
            DecisionCard.decision_id == decision_id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(404, f"Decision {decision_id} not found")
    return card


async def _emit(card: DecisionCard, event_type: str) -> None:
    await broadcast({
        "type": event_type,
        "decision_id": card.decision_id,
        "room_id": card.room_id,
        "task_id": card.task_id,
        "status": card.status,
        "decision_type": card.decision_type,
        "question": card.question,
        "source_agent_id": card.source_agent_id,
        "risk": card.risk,
    })


@router.post("", response_model=DecisionOut, status_code=201)
async def create_decision(
    body: DecisionCreate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    if not body.question.strip():
        raise HTTPException(422, "question is required")

    card = DecisionCard(
        team_id=team_id,
        decision_id=_new_decision_id(),
        room_id=body.room_id or "general",
        task_id=body.task_id,
        source_agent_id=body.source_agent_id,
        decision_type=body.decision_type or "clarify",
        question=body.question.strip(),
        context=body.context,
        options=body.options or [],
        recommended_option=body.recommended_option,
        risk=body.risk,
        confidence=body.confidence,
        cost_estimate=body.cost_estimate,
        deadline=body.deadline,
        status="pending",
    )
    _audit(card, "created", body.source_agent_id or "system")
    db.add(card)
    await db.commit()
    await db.refresh(card)
    await _emit(card, "decision_created")
    return card


@router.get("", response_model=list[DecisionOut])
async def list_decisions(
    status: str | None = Query(None),
    room_id: str | None = Query(None),
    task_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(DecisionCard).where(DecisionCard.team_id == team_id)
    if status:
        stmt = stmt.where(DecisionCard.status == status)
    if room_id:
        stmt = stmt.where(DecisionCard.room_id == room_id)
    if task_id:
        stmt = stmt.where(DecisionCard.task_id == task_id)
    stmt = stmt.order_by(DecisionCard.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{decision_id}", response_model=DecisionOut)
async def get_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    return await _get_card(db, team_id, decision_id)


@router.post("/{decision_id}/answer", response_model=DecisionOut)
async def answer_decision(
    decision_id: str,
    body: DecisionAnswer,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    if not body.answer.strip():
        raise HTTPException(422, "answer is required")
    card = await _get_card(db, team_id, decision_id)
    card.status = "answered"
    card.answer = body.answer.strip()
    card.note = body.note
    card.answered_by = body.answered_by or "human"
    card.answered_at = _now()
    card.updated_at = _now()
    _audit(card, "answered", card.answered_by, {"answer": card.answer, "note": card.note})
    await db.commit()
    await db.refresh(card)
    await _emit(card, "decision_updated")
    return card


@router.post("/{decision_id}/snooze", response_model=DecisionOut)
async def snooze_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    card = await _get_card(db, team_id, decision_id)
    card.status = "snoozed"
    card.updated_at = _now()
    _audit(card, "snoozed", "human")
    await db.commit()
    await db.refresh(card)
    await _emit(card, "decision_updated")
    return card


@router.post("/{decision_id}/delegate", response_model=DecisionOut)
async def delegate_decision(
    decision_id: str,
    body: DecisionDelegate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    if not body.delegate_to.strip():
        raise HTTPException(422, "delegate_to is required")
    card = await _get_card(db, team_id, decision_id)
    card.status = "delegated"
    card.delegated_to = body.delegate_to.strip()
    card.note = body.note
    card.updated_at = _now()
    _audit(card, "delegated", "human", {"to": card.delegated_to, "note": card.note})
    await db.commit()
    await db.refresh(card)
    await _emit(card, "decision_updated")
    return card
