"""
Telegram 알림 서비스.

TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 없으면 모두 no-op.
"""

import os
import logging

import httpx

log = logging.getLogger(__name__)

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

_BASE = "https://api.telegram.org"


def _enabled() -> bool:
    return bool(_BOT_TOKEN and _CHAT_ID)


async def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Telegram 그룹에 메시지 전송. 실패해도 예외를 올리지 않는다."""
    if not _enabled():
        return False
    url = f"{_BASE}/bot{_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(url, json={
                "chat_id": _CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
            })
            if not r.is_success:
                log.warning("Telegram sendMessage failed: %s", r.text)
                return False
        return True
    except Exception as exc:
        log.warning("Telegram sendMessage error: %s", exc)
        return False


async def notify_task_done(task_id: str, subject: str, pr_url: str | None = None) -> None:
    """태스크 완료 알림 전송."""
    pr_part = f'\n🔗 <a href="{pr_url}">PR 보기</a>' if pr_url else ""
    await send_message(
        f"✅ <b>태스크 완료</b>\n"
        f"<code>{task_id}</code>  {subject}{pr_part}"
    )


async def notify_task_error(task_id: str, subject: str) -> None:
    """태스크 오류 알림 전송."""
    await send_message(
        f"⚠️ <b>태스크 오류</b>\n"
        f"<code>{task_id}</code>  {subject}"
    )
