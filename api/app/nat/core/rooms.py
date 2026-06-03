"""Room / Message (M8 / Core) — agentic Slack의 typed 채널 + 채팅 아닌 typed event.

room = 조직 객체(goal/task/run/permission/memory)에 붙는 채널. message = 누가/어느 room에서/무엇을 기준으로
어떤 intent의 event를 남겼나. 모든 message는 EventLog에도 기록(통합 event 스트림). **message ≠ 실행** —
실행은 CommandProposal confirm을 거쳐야만(proposals.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contracts import Event, Message, Room

# message_type → 공통 EventType(append-only org event)
_MSG_EVENT = {
    "discussion.message": "discussion.message",
    "decision.proposal": "decision.proposed",
    "command.proposal": "discussion.message",
    "system": "discussion.message",
}


class RoomStore:
    def __init__(self, store_root: str | Path):
        self.dir = Path(store_root) / "rooms"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, room_id: str) -> Path:
        return self.dir / f"{room_id}.json"

    def create(self, room: Room) -> Room:
        self._path(room.room_id).write_text(room.model_dump_json(indent=2), encoding="utf-8")
        return room

    def get(self, room_id: str) -> Optional[Room]:
        p = self._path(room_id)
        return Room.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def list(self) -> list[Room]:
        return [Room.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(self.dir.glob("*.json"))]


class MessageLog:
    """append-only JSONL. post는 message 기록 + 공통 Event 방출(EventLog). 1라인=1 message."""

    def __init__(self, store_root: str | Path):
        self.root = Path(store_root)
        self.path = self.root / "messages" / "messages.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def post(self, message: Message) -> Message:
        from .eventlog import EventLog
        with self.path.open("a", encoding="utf-8") as f:
            f.write(message.model_dump_json() + "\n")
        EventLog(self.root).append(Event(
            event_type=_MSG_EVENT.get(message.message_type, "discussion.message"),
            producer=message.sender.id, message=message.body[:200],
            payload={"message_id": message.message_id, "room_id": message.room_id}))
        return message

    def all(self) -> list[Message]:
        if not self.path.exists():
            return []
        return [Message.model_validate_json(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read(self, room_id: str) -> list[Message]:
        return [m for m in self.all() if m.room_id == room_id]
