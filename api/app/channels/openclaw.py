"""openclaw ChannelAdapter (W4, 스텁).

Telegram 등 openclaw 메시지 → ChannelMessage(human intent). openclaw onboard/pairing/발화자
인증은 openclaw 쪽 책임이고, Dipeen은 pairing ≈ 팀 invite+JWT로 매핑한다(§10.5).
실제 전송 연동(WSS/webhook → Spine)은 후속 — 여기선 *정규화 계약*만 고정한다.
태스크 생성 경로를 의도적으로 두지 않는다(§7.5 불변).
"""
from __future__ import annotations

from .base import ChannelMessage


class OpenclawChannelAdapter:
    name = "openclaw"

    def to_message(self, platform_event: dict) -> ChannelMessage:
        e = platform_event or {}
        return ChannelMessage(
            channel=self.name,
            room_id=e.get("room_id") or e.get("chat_id") or "general",
            speaker=e.get("speaker") or e.get("from") or "unknown",
            text=e.get("text") or e.get("message") or "",
            raw=e,
        )
