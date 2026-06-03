"""Inbound NAT (M3 / §10) — RawAgentOutput → NormalizedAgentResult.

Core는 provider를 모른다 — 이름으로 플러그인을 찾아 parse_*를 위임하고 결과를 조립할 뿐.
artifacts를 먼저 파싱해 events에 넘긴다(event가 실제 artifact_id 참조). permission/memory는 M5/M7.
"""
from __future__ import annotations

from ..contracts import NormalizedAgentResult, RawAgentOutput
from .registry import get_plugin


def normalize(raw: RawAgentOutput, *, provider: str, task_id: str) -> NormalizedAgentResult:
    """provider raw output을 Dipeen 공통 계약(events/artifacts/state_claims)으로 정규화."""
    plugin = get_plugin(provider)
    artifacts = plugin.parse_artifacts(raw, task_id=task_id)
    state_claims = plugin.parse_state_claims(raw, task_id=task_id)
    events = plugin.parse_events(raw, task_id=task_id, artifacts=artifacts)
    # provider별 선택 파서(hermes 등): memory/skill candidates. 없는 provider(claude/codex/fake)는 빈 리스트.
    mem = plugin.parse_memory_candidates(raw) if hasattr(plugin, "parse_memory_candidates") else []
    skills = plugin.parse_skill_candidates(raw) if hasattr(plugin, "parse_skill_candidates") else []
    return NormalizedAgentResult(
        events=events,
        artifacts=artifacts,
        state_claims=state_claims,
        permission_requests=[],        # M5 Permission NAT
        memory_candidates=mem,         # hermes memory write → candidate(자동승격 금지)
        skill_candidates=skills,       # hermes skill create → candidate
    )
