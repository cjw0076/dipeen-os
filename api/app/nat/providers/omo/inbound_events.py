"""OMO inbound events (M11e) — team message/announcement raw_event → discussion.message Event.

독립 파서(claude/codex의 cli_common과 달리 omo는 raw_events가 풍부 — team mailbox/tool 이벤트).
OmoAdapter가 omo run의 event stream을 raw_events(kind=message|task|review|final 정규화)로 담는다.
"""
from __future__ import annotations

from ...contracts import Artifact, Event, RawAgentOutput
from .subtask_mapping import subtask_events


def omo_events(raw: RawAgentOutput, *, task_id: str, artifacts: list[Artifact]) -> list[Event]:
    out: list[Event] = []
    producer = raw.identity_id or "agent://team/omo"
    for ev in raw.raw_events:
        if ev.get("kind") == "message":               # team_send_message → 방 안의 typed message
            out.append(Event(
                event_type="discussion.message", task_id=task_id, run_id=raw.run_id, producer=producer,
                message=str(ev.get("content", ""))[:500],
                payload={"from": ev.get("from"), "to": ev.get("to")}))
    out += subtask_events(raw, task_id=task_id)        # team_task → provider.subtask (Dipeen Task 아님)
    return out
