"""OMO inbound state (M11e) — final raw_event → StateClaim(*주장*).

금지(사용자 스펙): OMO는 TaskState를 직접 바꾸지 않는다. final response는 StateClaim(claimed_state)일 뿐 —
실제 TaskState는 Reconciler가 evidence/acceptance로 결정한다(StateClaim≠TaskState, §2.3).
"""
from __future__ import annotations

from ...contracts import RawAgentOutput, StateClaim


def omo_state_claims(raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
    out: list[StateClaim] = []
    for ev in raw.raw_events:
        if ev.get("kind") == "final":
            out.append(StateClaim(
                task_id=task_id, run_id=raw.run_id or "",
                producer=raw.identity_id or "agent://team/omo",
                claimed_state="done" if ev.get("success") else "failed",   # 주장일 뿐
                message=str(ev.get("summary", ""))[:300]))
    return out
