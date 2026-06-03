"""channels — ChannelAdapter 패키지 (W4). 외부 채널을 HQ로 *입력만* 넘긴다(task 생성 X)."""
from .base import ChannelAdapter, ChannelMessage
from .openclaw import OpenclawChannelAdapter

__all__ = ["ChannelAdapter", "ChannelMessage", "OpenclawChannelAdapter"]
