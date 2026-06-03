"""Claude NAT plugin (M3) — claude 고유 번역. 실행만은 adapters/claude.py, 번역은 여기.

provider 고유: 구독 기본(ANTHROPIC_API_KEY="" → M2 adapter가 unset, 크레딧0). 파싱은 cli_common 공유
(M2가 RawAgentOutput로 정규화해 줌). raw_events가 풍부해지면 여기에 claude 전용 event 파서를 추가.
"""
from __future__ import annotations

from typing import Optional

from ...contracts import AgentInvocation, Artifact, Event, RawAgentOutput, StateClaim, TaskEnvelope
from .. import cli_common

_HEADER = "당신은 Dipeen 팀의 실행 에이전트입니다. 아래 Task를 워크스페이스에서 수행하세요.\n"


class ClaudeNATPlugin:
    name = "claude"
    adapter = "claude"

    def to_invocation(self, task: TaskEnvelope, *, run_id: str, identity_id: str,
                      workspace_root: str, context_pack: Optional[str] = None) -> AgentInvocation:
        return AgentInvocation(
            run_id=run_id, identity_id=identity_id,
            prompt=_HEADER + "\n" + cli_common.render_task_prompt(task, context_pack=context_pack),
            workspace_root=workspace_root,
            env={"ANTHROPIC_API_KEY": ""},          # 구독 기본 — BYOK는 M5 policy override
        )

    def parse_artifacts(self, raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
        return cli_common.cli_artifacts(raw, task_id=task_id, adapter=self.adapter)

    def parse_state_claims(self, raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
        return cli_common.cli_state_claims(raw, task_id=task_id)

    def parse_events(self, raw: RawAgentOutput, *, task_id: str,
                     artifacts: list[Artifact]) -> list[Event]:
        return cli_common.cli_events(raw, task_id=task_id, artifacts=artifacts)
