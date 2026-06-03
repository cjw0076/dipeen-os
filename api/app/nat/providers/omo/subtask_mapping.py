"""OMO subtask 매핑 (M11e) — team_task raw_event → provider.subtask Event.

금지(사용자 스펙): **OMO 내부 subtask를 바로 Dipeen Task로 만들지 않는다.** subtask는 provider-local로
머물고 Event(provider.subtask)로만 관찰된다 — TaskEnvelope/Run을 생성하지 않는다. Dipeen Task 생성은
회의→proposal→confirm 경로뿐(M8). omo team_task는 omo 내부 조율 단위일 뿐이다.
"""
from __future__ import annotations

from ...contracts import Event, RawAgentOutput


def subtask_events(raw: RawAgentOutput, *, task_id: str) -> list[Event]:
    out: list[Event] = []
    for ev in raw.raw_events:
        if ev.get("kind") == "task":
            out.append(Event(
                event_type="provider.subtask", task_id=task_id, run_id=raw.run_id,
                producer=raw.identity_id or "agent://team/omo",
                message=f"omo subtask {ev.get('task_id')} [{ev.get('status')}] {ev.get('title', '')}"[:200],
                payload={"provider_task_id": ev.get("task_id"), "status": ev.get("status"),
                         "title": ev.get("title")}))   # provider-local — Dipeen Task 아님
    return out
