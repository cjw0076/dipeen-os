"""Meeting Room — WS 이벤트 브로드캐스트 프록시 + 상태 복구 API."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.routers.events import broadcast

router = APIRouter()

# 방별 회의 상태 저장소 (pm_loop이 POST /state 로 동기화)
_MEETING_STORE: dict[str, dict] = {}


class BroadcastBody(BaseModel):
    event: dict[str, Any]


class MeetingStateBody(BaseModel):
    room_id: str
    phase: str
    mode: str = "plan"
    brief: dict | None = None
    participants: list[dict] = []


class MeetingModeBody(BaseModel):
    room_id: str
    mode: str  # "plan" | "brainstorm"


@router.post("/broadcast")
async def broadcast_event(body: BroadcastBody):
    """pm_loop → API → WS 브로드캐스트 프록시."""
    await broadcast(body.event)
    return {"ok": True}


@router.post("/state")
async def set_state(body: MeetingStateBody):
    """pm_loop이 현재 회의 상태를 동기화 (WS 재연결 복구용)."""
    _MEETING_STORE[body.room_id] = {
        **body.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True}


@router.post("/mode")
async def set_mode(body: MeetingModeBody):
    """UI 모드 셀렉터 → pm_loop에 WS 이벤트로 전달."""
    valid = {"plan", "brainstorm", "review", "debate"}
    if body.mode not in valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"mode must be one of {valid}")

    # 현재 저장된 상태에 mode 반영
    stored = _MEETING_STORE.setdefault(body.room_id, {})
    stored["mode"] = body.mode
    stored["updated_at"] = datetime.now(timezone.utc).isoformat()

    # pm_loop WS 클라이언트에게 브로드캐스트
    await broadcast({
        "type": "meeting_mode",
        "room_id": body.room_id,
        "mode": body.mode,
    })
    return {"ok": True, "mode": body.mode}


@router.get("/state")
async def get_state(room_id: str = "general"):
    """클라이언트 WS 재연결 시 현재 회의 상태 복구."""
    stored = _MEETING_STORE.get(room_id)
    if stored:
        # mode 필드 없는 구버전 저장 데이터 보완
        return {**stored, "mode": stored.get("mode", "plan")}
    return {
        "room_id": room_id,
        "phase": "DISCUSSING",
        "mode": "plan",
        "brief": None,
        "participants": [],
    }


# ── P3: PM Agent 설정 ──────────────────────────────────────────

_PM_CONFIG: dict = {
    "pm_name": "PM Agent",
    "response_style": "detailed",   # "concise" | "detailed"
    "auto_execute": False,          # True면 확인 단계 스킵
}


class PMConfigBody(BaseModel):
    pm_name: str | None = None
    response_style: str | None = None
    auto_execute: bool | None = None
    skip_review: bool | None = None  # OPT-2: SPEAK/PASS 스킵


@router.get("/pm-config")
async def get_pm_config():
    return _PM_CONFIG


@router.put("/pm-config")
async def set_pm_config(body: PMConfigBody):
    if body.pm_name is not None:
        _PM_CONFIG["pm_name"] = body.pm_name
    if body.response_style is not None:
        if body.response_style in ("concise", "detailed"):
            _PM_CONFIG["response_style"] = body.response_style
    if body.auto_execute is not None:
        _PM_CONFIG["auto_execute"] = body.auto_execute
    if body.skip_review is not None:
        _PM_CONFIG["skip_review"] = body.skip_review
    # pm_loop에 설정 변경 브로드캐스트
    await broadcast({
        "type": "pm_config_update",
        **_PM_CONFIG,
    })
    return _PM_CONFIG
