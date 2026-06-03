"""ClaudeAdapter (M2) — claude CLI 비대화 실행만(`claude -p PROMPT`).

구독/BYOK 선택은 invocation.env로 제어(구독=ANTHROPIC_API_KEY="" → ~/.claude 자격증명).
어댑터는 artifact/state를 만들지 않는다 — RawAgentOutput만(§10 Isolation).
"""
from __future__ import annotations

from ..contracts import AgentInvocation
from .base import CliExecAdapter


class ClaudeAdapter(CliExecAdapter):
    name = "claude"
    cli = "claude"

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        # claude -p [extra…] <prompt>. extra_args=권한우회 등(예: --dangerously-skip-permissions)
        return self._base_argv() + ["-p"] + self.extra_args + [invocation.prompt]
