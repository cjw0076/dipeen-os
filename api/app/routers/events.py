"""
WebSocket 이벤트 허브.

단일 인스턴스: in-process Set[WebSocket]으로 브로드캐스트.
다중 인스턴스: REDIS_URL 설정 시 Redis pub/sub으로 수평 확장.

broadcast()를 다른 라우터에서 호출해 이벤트를 전파한다.
"""

import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_connections: List[WebSocket] = []
_CHANNEL = "dipeen:events"

# ── Redis pub/sub (REDIS_URL 있을 때만 활성화) ────────────────────

_redis_pub = None   # publish 전용 client
_redis_task = None  # subscribe 루프 태스크


async def _init_redis() -> None:
    """lifespan에서 호출 — Redis 연결 및 subscriber 시작."""
    global _redis_pub, _redis_task
    url = settings.redis_url
    if not url:
        return
    try:
        import redis.asyncio as aioredis  # type: ignore
        _redis_pub = aioredis.from_url(url, decode_responses=True)
        await _redis_pub.ping()
        _redis_task = asyncio.create_task(_redis_subscriber(url))
        logger.info("Redis pub/sub enabled: %s", url)
    except Exception as e:
        logger.warning("Redis init failed (%s) -- falling back to in-process", e)
        _redis_pub = None


async def _redis_subscriber(url: str) -> None:
    """Redis 채널을 구독, 메시지가 오면 로컬 WS 클라이언트에 전달."""
    try:
        import redis.asyncio as aioredis  # type: ignore
        sub = aioredis.from_url(url, decode_responses=True)
        async with sub.pubsub() as ps:
            await ps.subscribe(_CHANNEL)
            async for msg in ps.listen():
                if msg["type"] != "message":
                    continue
                await _broadcast_local(msg["data"])
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Redis subscriber error: %s", e)


async def _close_redis() -> None:
    global _redis_pub, _redis_task
    if _redis_task:
        _redis_task.cancel()
        _redis_task = None
    if _redis_pub:
        await _redis_pub.aclose()
        _redis_pub = None


# ── 브로드캐스트 ──────────────────────────────────────────────────

async def _broadcast_local(msg: str) -> None:
    """이 프로세스에 연결된 모든 WS 클라이언트에게 전송."""
    if not _connections:
        return
    dead: List[WebSocket] = []
    for ws in list(_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connections:
            _connections.remove(ws)


async def broadcast(event: dict) -> None:
    """이벤트를 전체 클라이언트에게 전파.

    Redis 설정 시: Redis pub/sub → 모든 인스턴스의 subscriber → 로컬 WS
    미설정 시:     in-process 직접 전송
    """
    msg = json.dumps(event, default=str)
    if _redis_pub is not None:
        try:
            await _redis_pub.publish(_CHANNEL, msg)
            return
        except Exception as e:
            logger.warning("Redis publish failed: %s -- falling back", e)
    await _broadcast_local(msg)


# ── WebSocket 엔드포인트 ──────────────────────────────────────────

@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    _connections.append(ws)
    logger.info("WS connected. total=%d", len(_connections))
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connections:
            _connections.remove(ws)
        logger.info("WS disconnected. total=%d", len(_connections))
