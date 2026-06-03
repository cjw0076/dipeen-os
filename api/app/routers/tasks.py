import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task
from app.db.session import get_db
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.routers.events import broadcast
from app.routers.auth import get_team_id, require_owner
from app.services import telegram
from app.services import control_plane

router = APIRouter()

# K-2: in-memory 질문/답변 저장 (transient — 서버 재시작 시 초기화)
_pending_questions: dict[str, dict] = {}
_pending_answers: dict[str, str] = {}


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    task_id = f"T-{uuid.uuid4()}"
    branch = body.branch or f"feat/{task_id}"

    # blocked_by가 있으면 "blocked" 상태로 시작 (선행 태스크 완료 후 자동 해제)
    initial_status = "blocked" if body.blocked_by else "pending"

    task = Task(
        team_id=team_id,
        task_id=task_id,
        subject=body.subject,
        prompt=body.prompt,
        branch=branch,
        complexity=body.complexity,
        required_role=body.required_role,
        required_skills=body.required_skills or [],
        required_persona=body.required_persona,
        parent_task_id=body.parent_task_id,
        blocked_by=body.blocked_by,
        created_by_agent=body.created_by_agent,
        status=initial_status,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    nat_event = control_plane.record_task_created(task)
    await broadcast({
        "type": "task_update",
        "task_id": task.task_id,
        "status": "pending",
        "subject": task.subject,
    })
    await broadcast({
        "type": "event.created",
        "event_id": nat_event.event_id,
        "event_type": nat_event.event_type,
        "task_id": task.task_id,
    })
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = Query(None),
    parent_task_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(Task).where(Task.team_id == team_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if parent_task_id:
        stmt = stmt.where(Task.parent_task_id == parent_task_id)
    stmt = stmt.order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(Task).where(Task.task_id == task_id, Task.team_id == team_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    stmt = select(Task).where(Task.task_id == task_id, Task.team_id == team_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    prev_status = task.status

    # S-1: retry — error/cancelled 태스크를 pending으로 리셋
    if body.retry and task.status in ("error", "cancelled"):
        task.status = "pending"
        task.assigned_agent_id = None
        task.completed_at = None
        task.result = None
        task.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(task)
        nat_event = control_plane.record_task_state(task, event_type="task.retry_requested")
        await broadcast({
            "type": "task_update",
            "task_id": task.task_id,
            "status": "pending",
        })
        await broadcast({
            "type": "event.created",
            "event_id": nat_event.event_id,
            "event_type": nat_event.event_type,
            "task_id": task.task_id,
        })
        return task

    if body.status is not None:
        task.status = body.status
        if body.status in ("done", "error", "cancelled"):
            task.completed_at = datetime.now(timezone.utc)
    if body.pr_url is not None:
        task.pr_url = body.pr_url
    if body.result is not None:
        task.result = body.result
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    nat_event = control_plane.record_task_state(task)
    await broadcast({
        "type": "task_update",
        "task_id": task.task_id,
        "status": task.status,
        "pr_url": task.pr_url,
    })
    await broadcast({
        "type": "event.created",
        "event_id": nat_event.event_id,
        "event_type": nat_event.event_type,
        "task_id": task.task_id,
    })

    # 완료 시: 이 태스크에 블록된 태스크들 자동 해제
    if task.status == "done" and prev_status != "done":
        await _unblock_dependents(db, task.task_id)

    # Telegram 알림 (환경변수 없으면 no-op)
    if prev_status != task.status:
        if task.status == "done":
            await telegram.notify_task_done(task.task_id, task.subject, task.pr_url)
        elif task.status == "error":
            await telegram.notify_task_error(task.task_id, task.subject)

    return task


async def _unblock_dependents(db: AsyncSession, completed_task_id: str) -> None:
    """완료된 태스크에 blocked_by로 묶인 태스크들을 pending으로 전환."""
    stmt = select(Task).where(
        Task.blocked_by == completed_task_id,
        Task.status == "blocked",
    )
    result = await db.execute(stmt)
    unblocked = result.scalars().all()
    if not unblocked:
        return

    now = datetime.now(timezone.utc)
    for t in unblocked:
        t.status = "pending"
        t.blocked_by = None
        t.updated_at = now

    await db.commit()

    for t in unblocked:
        await broadcast({
            "type": "task_update",
            "task_id": t.task_id,
            "status": "pending",
            "unblocked_by": completed_task_id,
        })


class QuestionBody(BaseModel):
    question: str
    context: str | None = None
    options: list[str] = []


class AnswerBody(BaseModel):
    answer: str


@router.post("/{task_id}/question")
async def post_task_question(task_id: str, body: QuestionBody):
    """K-2: 에이전트가 작업 중 질문 등록 → 웹 UI에 broadcast."""
    _pending_questions[task_id] = {
        "question": body.question,
        "context": body.context,
        "options": body.options,
    }
    await broadcast({
        "type": "task_question",
        "task_id": task_id,
        "question": body.question,
        "context": body.context,
        "options": body.options,
    })
    return {"ok": True}


@router.post("/{task_id}/answer")
async def post_task_answer(task_id: str, body: AnswerBody):
    """K-2: 사용자가 웹 UI에서 답변 제출."""
    _pending_answers[task_id] = body.answer
    _pending_questions.pop(task_id, None)
    await broadcast({
        "type": "task_answer",
        "task_id": task_id,
    })
    return {"ok": True}


@router.get("/{task_id}/answer")
async def get_task_answer(task_id: str, timeout: int = Query(30, le=60)):
    """K-2: runtime.py long-poll — 답변이 올 때까지 대기 (최대 timeout초)."""
    for _ in range(min(timeout, 60)):
        if task_id in _pending_answers:
            answer = _pending_answers.pop(task_id)
            return {"answer": answer}
        await asyncio.sleep(1)
    return {"answer": None}


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
    _: None = Depends(require_owner),
):
    stmt = select(Task).where(Task.task_id == task_id, Task.team_id == team_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    if task.status not in ("pending", "in_progress"):
        raise HTTPException(400, f"Task {task_id} is already {task.status}")

    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)

    nat_event = control_plane.record_task_state(task)
    await broadcast({
        "type": "task_update",
        "task_id": task.task_id,
        "status": "cancelled",
    })
    await broadcast({
        "type": "event.created",
        "event_id": nat_event.event_id,
        "event_type": nat_event.event_type,
        "task_id": task.task_id,
    })
    return task
