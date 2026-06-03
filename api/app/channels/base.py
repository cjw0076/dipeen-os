"""ChannelAdapter (W4) — 외부 채널(openclaw / hermes gateway)을 HQ로 *입력만* 넘긴다.

원칙(study-guide §7.5, 안티패턴 #2): **채널 메시지는 태스크를 직접 생성하지 않는다.**
흐름: 외부 메시지 → ChannelAdapter → ChannelMessage(human intent) → Spine/chat
→ (선택) PM DISCUSSING → proposed_plan → 사용자 승인 → tasks 생성(HQ만).
openclaw가 task truth를 가지면 멀티테넌트·역할 RBAC가 붕괴한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ChannelMessage:
    """채널에서 들어온 *사람 의도*. 태스크가 아니다(creates_tasks=False 고정)."""
    channel: str               # "openclaw" | "hermes-gateway"
    room_id: str
    speaker: str               # 인증된 발화자 id (openclaw pairing ≈ 팀 invite/JWT, §10.5)
    text: str
    raw: dict = field(default_factory=dict)
    creates_tasks: bool = field(default=False, init=False)   # 불변: 채널은 task를 못 만든다


@runtime_checkable
class ChannelAdapter(Protocol):
    """플랫폼 이벤트를 ChannelMessage로 정규화만 한다. task 생성 메서드를 두지 않는다."""
    name: str

    def to_message(self, platform_event: dict) -> ChannelMessage: ...
