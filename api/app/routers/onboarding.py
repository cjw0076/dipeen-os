"""
온보딩 라우터 (I-1-4).

POST /api/onboarding/seed  — 방 최초 입장 시 샘플 태스크 자동 생성.
GET  /api/onboarding/check — 방에 태스크/메시지가 있는지 확인 (최초 여부 판단).
"""

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from app.db.models import Task, ChatMessage
from app.db.session import async_session
from app.routers.events import broadcast

router = APIRouter()

DEFAULT_TEAM_ID = "default-team"

SAMPLE_TASKS = [
    {
        "subject": "[Hello] FE: Button 컴포넌트 추가",
        "prompt": (
            "src/components/Button.tsx 파일을 만들어 주세요. "
            "기본 props: label(string), onClick(handler), variant('primary'|'secondary'). "
            "Tailwind CSS로 스타일링. dipeen 온보딩 샘플 태스크입니다."
        ),
        "required_role": "FE",
    },
    {
        "subject": "[Hello] BE: /api/ping 엔드포인트 추가",
        "prompt": (
            "api/app/routers/ 에 ping.py를 만들어 주세요. "
            "GET /api/ping → {pong: true, ts: ISO timestamp}. "
            "dipeen 온보딩 샘플 태스크입니다."
        ),
        "required_role": "BE",
    },
]


class SeedBody(BaseModel):
    room_id: str = "general"
    role: str | None = None  # 특정 role만 시드할 때


@router.post("/seed")
async def seed_sample_tasks(body: SeedBody):
    """방 최초 입장 시 샘플 태스크 생성. 이미 태스크가 있으면 skip."""
    async with async_session() as db:
        # 이미 태스크가 있으면 skip
        count_result = await db.execute(
            select(func.count()).select_from(Task).where(Task.team_id == DEFAULT_TEAM_ID)
        )
        existing = count_result.scalar_one()
        if existing > 0:
            return {"ok": True, "seeded": 0, "skipped": True, "reason": "tasks already exist"}

        seeded = []
        for sample in SAMPLE_TASKS:
            if body.role and sample["required_role"] != body.role:
                continue
            task_id = f"T-{uuid.uuid4()}"
            task = Task(
                team_id=DEFAULT_TEAM_ID,
                task_id=task_id,
                subject=sample["subject"],
                prompt=sample["prompt"],
                branch=f"feat/{task_id}",
                required_role=sample["required_role"],
                status="pending",
                complexity="trivial",
            )
            db.add(task)
            seeded.append(task_id)

        await db.commit()

    # WS 브로드캐스트
    for task_id in seeded:
        await broadcast({
            "type": "task_update",
            "task_id": task_id,
            "status": "pending",
        })

    return {"ok": True, "seeded": len(seeded), "task_ids": seeded}


@router.get("/check")
async def check_onboarding(room_id: str = Query("general")):
    """방에 태스크 또는 메시지가 있는지 확인."""
    async with async_session() as db:
        task_count = (await db.execute(
            select(func.count()).select_from(Task).where(Task.team_id == DEFAULT_TEAM_ID)
        )).scalar_one()

        msg_count = (await db.execute(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.room_id == room_id)
        )).scalar_one()

    return {
        "room_id": room_id,
        "is_fresh": task_count == 0 and msg_count == 0,
        "task_count": task_count,
        "message_count": msg_count,
    }
