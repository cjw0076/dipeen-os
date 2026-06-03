"""
채팅 메시지 라우터.
Phase B: 인메모리 브로드캐스트.
Phase C: pm_loop가 "text" 필드로 전송, sender_type 구분 추가.
Phase I-2: DB 영속성 + GET /history 엔드포인트.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import select, desc

from app.routers.events import broadcast
from app.db.session import async_session
from app.db.models import ChatMessage as ChatMessageModel
from app.nat.contracts import Message, MessageLink, SenderRef
from app.services import control_plane

router = APIRouter()

HISTORY_LIMIT_MAX = 200

AGENT_COLORS = {
    "PM": "#FBBF24",
    "pm-agent": "#FBBF24",
    "pm-loop": "#FBBF24",
    "FE": "#60A5FA",
    "BE": "#34D399",
    "QA": "#A78BFA",
}

SENDER_COLOR_DEFAULT = {
    "user": "#FAFAFA",
    "agent": "#888888",
    "pm": "#FBBF24",
}


class ChatMessageBody(BaseModel):
    sender: str = "You"
    sender_type: Literal["user", "agent", "pm", "question"] = "user"
    room_id: str = "general"
    role: str | None = None        # K-1: 역할 약어 (FE/BE/QA/PM) → 색상 결정용
    task_id: str | None = None     # K-2: 질문 카드에서 어떤 태스크에 대한 질문인지 연결
    metadata_json: dict | None = None  # W-1: 구조화된 메타데이터
    # 두 필드 모두 허용 (text = pm_loop/frontend, content = 레거시)
    text: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def _normalize_text(self):
        self.text = self.text or self.content or ""
        return self


@router.post("/messages")
async def send_message(body: ChatMessageBody):
    ts = datetime.now(timezone.utc).strftime("%H:%M")
    msg_id = str(uuid.uuid4())[:8]
    color = AGENT_COLORS.get(
        body.role or "",
        AGENT_COLORS.get(body.sender, SENDER_COLOR_DEFAULT.get(body.sender_type, "#FAFAFA")),
    )

    msg_event = {
        "type": "chat_message",
        "id": msg_id,
        "sender": body.sender,
        "sender_type": body.sender_type,
        "room_id": body.room_id,
        "color": color,
        "text": body.text,
        "content": body.text,     # 레거시 호환
        "timestamp": ts,
        **({"task_id": body.task_id} if body.task_id else {}),
        **({"metadata_json": body.metadata_json} if body.metadata_json else {}),
    }
    await broadcast(msg_event)

    # DB 저장 (공백 메시지 제외)
    if body.text and body.text.strip():
        async with async_session() as db:
            db.add(ChatMessageModel(
                id=msg_id,
                room_id=body.room_id,
                sender=body.sender,
                sender_type=body.sender_type,
                color=color,
                text=body.text,
                task_id=body.task_id,
                metadata_json=body.metadata_json,
            ))
            await db.commit()
        try:
            control_plane.post_message(Message(
                room_id=body.room_id,
                sender=SenderRef(
                    type="human" if body.sender_type == "user" else "agent",
                    id=f"user://{body.sender}" if body.sender_type == "user" else f"agent://team/{body.sender}",
                ),
                message_type="discussion.message",
                body=body.text,
                links=[MessageLink(target_type="task", target_id=body.task_id)] if body.task_id else [],
            ))
        except Exception as e:
            print(f"[chat] NAT message append failed: {e}", flush=True)

    # 커맨드 처리 (사람 메시지에만)
    if body.sender_type == "user":
        text = (body.text or "").strip()
        if text.startswith("/status"):
            await broadcast({
                "type": "chat_message",
                "id": str(uuid.uuid4())[:8],
                "sender": "PM Alice",
                "sender_type": "pm",
                "color": AGENT_COLORS["PM"],
                "text": "현재 진행 중인 태스크를 확인할게요.",
                "content": "현재 진행 중인 태스크를 확인할게요.",
                "timestamp": ts,
            })
        elif text.startswith("/cancel"):
            parts = text.split()
            task_id = parts[1] if len(parts) > 1 else "?"
            await broadcast({
                "type": "chat_message",
                "id": str(uuid.uuid4())[:8],
                "sender": "PM Alice",
                "sender_type": "pm",
                "color": AGENT_COLORS["PM"],
                "text": f"{task_id} 취소 요청을 처리할게요.",
                "content": f"{task_id} 취소 요청을 처리할게요.",
                "timestamp": ts,
            })

    return {"ok": True, "id": msg_id}


@router.get("/history")
async def get_history(
    room_id: str = Query("general"),
    task_id: str | None = Query(None),  # W-4: 태스크별 메시지 필터
    sender: str | None = Query(None),   # W-5: 에이전트별 메시지 필터
    limit: int = Query(50, le=HISTORY_LIMIT_MAX),
):
    """최근 메시지 조회 (페이지 로드 시 채팅 복구)."""
    async with async_session() as db:
        stmt = select(ChatMessageModel).where(ChatMessageModel.room_id == room_id)
        if task_id:
            stmt = stmt.where(ChatMessageModel.task_id == task_id)
        if sender:
            stmt = stmt.where(ChatMessageModel.sender == sender)
        stmt = stmt.order_by(desc(ChatMessageModel.created_at)).limit(limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "id": m.id,
            "room_id": m.room_id,
            "sender": m.sender,
            "sender_type": m.sender_type,
            "color": m.color,
            "text": m.text,
            "task_id": m.task_id,
            "metadata_json": m.metadata_json,
            "created_at": m.created_at.isoformat(),
            "timestamp": m.created_at.strftime("%H:%M"),
        }
        for m in reversed(rows)
    ]
