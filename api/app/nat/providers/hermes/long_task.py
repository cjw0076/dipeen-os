"""Hermes inbound — cron/scheduled job 진행 → long_task.checkpoint Event (관찰).

hermes cron(jobs.json + output/{id}/{ts}.md)은 mid-execution 진행 이벤트가 없다(완료 후 파일). HermesAdapter가
job 완료/출력 파일을 raw_events(kind=cron_checkpoint)로 정규화 — long-running task의 관찰 가능한 진행점.
"""
from __future__ import annotations

from ...contracts import Event, RawAgentOutput


def hermes_long_task_events(raw: RawAgentOutput, *, task_id: str) -> list[Event]:
    out: list[Event] = []
    for ev in raw.raw_events:
        if ev.get("kind") == "cron_checkpoint":
            out.append(Event(
                event_type="long_task.checkpoint", task_id=task_id, run_id=raw.run_id,
                producer=raw.identity_id or "agent://team/hermes",
                message=f"cron {ev.get('job_id')}: {str(ev.get('output', ''))[:120]}",
                payload={"job_id": ev.get("job_id"), "output": str(ev.get("output", ""))[:500]}))
    return out
