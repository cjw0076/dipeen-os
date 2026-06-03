"""OMO(oh-my-opencode) provider — inspect(M11a)·probe(M11b)·NAT plugin(M11c–e) 공존."""
from __future__ import annotations

from ...contracts import AgentInvocation, Artifact, Event, RawAgentOutput, StateClaim, TaskEnvelope
from .. import cli_common
from .inbound_artifacts import omo_artifacts
from .inbound_events import omo_events
from .state_claims import omo_state_claims

_HEADER = "당신은 Dipeen 팀의 OMO 실행 에이전트입니다(team 조율 가능). 아래 Task를 워크스페이스에서 수행하세요.\n"


class OmoNATPlugin:
    """OMO NAT plugin — outbound render + inbound 독립 파서(team message/subtask/review/final).
    실행은 adapters/omo.py(omo run --json), 번역은 여기. claude/codex와 달리 raw_events가 풍부."""
    name = "omo"
    adapter = "omo"

    def to_invocation(self, task: TaskEnvelope, *, run_id: str, identity_id: str,
                      workspace_root: str, context_pack=None) -> AgentInvocation:
        return AgentInvocation(
            run_id=run_id, identity_id=identity_id,
            prompt=_HEADER + "\n" + cli_common.render_task_prompt(task, context_pack=context_pack),
            workspace_root=workspace_root, env={})

    def parse_artifacts(self, raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
        return omo_artifacts(raw, task_id=task_id)

    def parse_state_claims(self, raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
        return omo_state_claims(raw, task_id=task_id)

    def parse_events(self, raw: RawAgentOutput, *, task_id: str, artifacts: list[Artifact]) -> list[Event]:
        return omo_events(raw, task_id=task_id, artifacts=artifacts)
