"""NAT-hermes provider — inspect(M11a)·probe(M11b)·NAT plugin(M11c–e). 무관: legacy routers/hermes.py(A2A relay)."""
from __future__ import annotations

from ...contracts import AgentInvocation, Artifact, Event, RawAgentOutput, StateClaim, TaskEnvelope
from .. import cli_common
from .inbound_artifacts import hermes_artifacts
from .long_task import hermes_long_task_events
from .memory_candidate import hermes_memory_candidates
from .skill_candidate import hermes_skill_candidates

_HEADER = "당신은 Dipeen 팀의 Hermes 에이전트입니다. 아래 Task를 수행하세요(memory/skill은 candidate로만 — 자동승격 금지).\n"


class HermesNATPlugin:
    """Hermes NAT plugin — outbound render + inbound(memory/skill candidate, cron checkpoint, retrieval)."""
    name = "hermes"
    adapter = "hermes"

    def to_invocation(self, task: TaskEnvelope, *, run_id: str, identity_id: str,
                      workspace_root: str, context_pack=None) -> AgentInvocation:
        return AgentInvocation(
            run_id=run_id, identity_id=identity_id,
            prompt=_HEADER + "\n" + cli_common.render_task_prompt(task, context_pack=context_pack),
            workspace_root=workspace_root, env={})

    def parse_artifacts(self, raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
        return hermes_artifacts(raw, task_id=task_id)

    def parse_state_claims(self, raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
        return []

    def parse_events(self, raw: RawAgentOutput, *, task_id: str, artifacts: list[Artifact]) -> list[Event]:
        return hermes_long_task_events(raw, task_id=task_id)

    def parse_memory_candidates(self, raw: RawAgentOutput):
        return hermes_memory_candidates(raw)

    def parse_skill_candidates(self, raw: RawAgentOutput):
        return hermes_skill_candidates(raw)
