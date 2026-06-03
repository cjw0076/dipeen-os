"""HermesAdapter (M11d) — `hermes -z PROMPT` oneshot 실행만(CliExecAdapter). plain-text stdout → final.

실측: hermes oneshot은 구조화 출력 없이 최종 텍스트만 준다 + credential 필요(없으면 비0 exit 정직).
memory/skill/cron의 풍부한 raw_events는 파일 폴링/custom provider(범위 밖) — oneshot은 final만 관찰 가능.
"""
from __future__ import annotations

from ..contracts import AgentInvocation, RawAgentOutput
from .base import CliExecAdapter


class HermesAdapter(CliExecAdapter):
    name = "hermes"
    cli = "hermes"

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        return self._base_argv() + ["-z", invocation.prompt] + self.extra_args

    async def run(self, invocation: AgentInvocation) -> RawAgentOutput:
        raw = await super().run(invocation)
        if raw.exit_code == 0 and raw.stdout.strip():
            raw.raw_events = [{"kind": "final", "success": True, "summary": raw.stdout.strip()[:500]}]
        return raw
