"""Codex NAT plugin (M3) — codex 고유 번역. 실행만은 adapters/codex.py, 번역은 여기.

provider 고유: codex는 `codex login` / OPENAI_API_KEY 기반이라 ANTHROPIC 키를 건드리지 않는다(env 분기).
파싱은 cli_common 공유(M2가 RawAgentOutput로 정규화). codex exec 세션 포맷이 풍부해지면 전용 파서 추가.
"""
from __future__ import annotations

from typing import Optional

from ...contracts import AgentInvocation, Artifact, Event, RawAgentOutput, StateClaim, TaskEnvelope
from .. import cli_common

_HEADER = "You are a Dipeen team execution agent. Complete the following Task in the workspace.\n"


class CodexNATPlugin:
    name = "codex"
    adapter = "codex"

    def to_invocation(self, task: TaskEnvelope, *, run_id: str, identity_id: str,
                      workspace_root: str, context_pack: Optional[str] = None) -> AgentInvocation:
        return AgentInvocation(
            run_id=run_id, identity_id=identity_id,
            prompt=_HEADER + "\n" + cli_common.render_task_prompt(task, context_pack=context_pack),
            workspace_root=workspace_root,
            env={},                                  # codex login / OPENAI_API_KEY — ANTHROPIC 무관
        )

    def parse_artifacts(self, raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
        return cli_common.cli_artifacts(raw, task_id=task_id, adapter=self.adapter)

    def parse_state_claims(self, raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
        return cli_common.cli_state_claims(raw, task_id=task_id)

    def parse_events(self, raw: RawAgentOutput, *, task_id: str,
                     artifacts: list[Artifact]) -> list[Event]:
        return cli_common.cli_events(raw, task_id=task_id, artifacts=artifacts)
