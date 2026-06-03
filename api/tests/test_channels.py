"""W4 — ChannelAdapter(openclaw): 정규화 + §7.5 불변(채널은 태스크를 만들지 않는다)."""
from app.channels.base import ChannelMessage
from app.channels.openclaw import OpenclawChannelAdapter


def test_openclaw_normalizes_to_human_intent():
    a = OpenclawChannelAdapter()
    msg = a.to_message({"chat_id": "room-9", "from": "alice", "text": "배포 좀 봐줘"})
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "openclaw"
    assert msg.room_id == "room-9"
    assert msg.speaker == "alice"
    assert msg.text == "배포 좀 봐줘"


def test_channel_never_creates_tasks():
    # §7.5 불변: 채널 메시지는 태스크를 직접 만들지 않는다 — HQ(PM+승인)만.
    a = OpenclawChannelAdapter()
    msg = a.to_message({"text": "x"})
    assert msg.creates_tasks is False
    # 어댑터 표면에 task 생성 메서드가 없어야 한다(룰을 코드로 강제).
    assert not any("task" in m.lower() for m in dir(a))


def test_defaults_when_fields_missing():
    msg = OpenclawChannelAdapter().to_message({})
    assert msg.room_id == "general" and msg.speaker == "unknown" and msg.text == ""
