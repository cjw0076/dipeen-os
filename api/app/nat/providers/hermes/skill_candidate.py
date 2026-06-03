"""Hermes inbound — skill creation(skill_manage create) → SkillCandidate. 자동승격 금지(requires_review).

hermes는 SKILL.md 파일을 생성하지만 Dipeen은 후보로만 수용(candidate→review→promote). HermesAdapter가
skill_manage tool-call/파일 생성을 raw_events(kind=skill_create)로 정규화한다.
"""
from __future__ import annotations

from ...contracts import RawAgentOutput, SkillCandidate


def hermes_skill_candidates(raw: RawAgentOutput) -> list[SkillCandidate]:
    out: list[SkillCandidate] = []
    for ev in raw.raw_events:
        if ev.get("kind") == "skill_create":
            out.append(SkillCandidate(
                name=str(ev.get("name", "")),
                description=str(ev.get("content", ""))[:300],
                promotion_policy="requires_review"))
    return out
