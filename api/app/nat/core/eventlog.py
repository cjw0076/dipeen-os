"""EventLog (M1 / §9) — append-only JSONL. 현재 상태는 *덮어쓰지* 않고 event를 replay해서 만든다.

1 라인 = 1 Event(JSON). 동시쓰기는 append 모드라 안전(라인 원자성). 대규모면 후에 event log를 DB로.
"""
from __future__ import annotations

from pathlib import Path

from ..contracts import Event


class EventLog:
    def __init__(self, root: str | Path):
        self.path = Path(root) / "events" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> Event:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
        return event

    def append_all(self, events: list[Event]) -> None:
        if not events:
            return
        with self.path.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(e.model_dump_json() + "\n")

    def read_all(self) -> list[Event]:
        if not self.path.exists():
            return []
        out: list[Event] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(Event.model_validate_json(line))
        return out

    def by_task(self, task_id: str) -> list[Event]:
        return [e for e in self.read_all() if e.task_id == task_id]

    def tail(self, n: int = 50) -> list[Event]:
        return self.read_all()[-n:]
