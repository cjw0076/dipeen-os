"""Hermes inbound — memory write(memory_tool add/replace) → MemoryCandidate. **자동승격 금지**.

금지(사용자 스펙): Hermes memory를 바로 Organization Memory로 넣지 않는다. memory write는 candidate일 뿐 —
candidate→review→promote(M7). hermes는 MEMORY.md/USER.md 파일에 쓰지만 Dipeen은 *후보*로만 수용한다.
HermesAdapter가 on_memory_write hook/파일 diff를 raw_events(kind=memory_write)로 정규화한다.
"""
from __future__ import annotations

from ...contracts import MemoryCandidate, RawAgentOutput

_TARGET_TO_MEMTYPE = {"memory": "project", "user": "personal"}


def hermes_memory_candidates(raw: RawAgentOutput) -> list[MemoryCandidate]:
    out: list[MemoryCandidate] = []
    for ev in raw.raw_events:
        if ev.get("kind") == "memory_write" and ev.get("action") in ("add", "replace"):
            out.append(MemoryCandidate(
                memory_type=_TARGET_TO_MEMTYPE.get(ev.get("target", "memory"), "project"),
                proposed_content=str(ev.get("content", "")),
                promotion_policy="requires_review"))   # 자동승격 금지 — 사람/정책 review 후에만 promote
    return out
