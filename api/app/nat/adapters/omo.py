"""OmoAdapter (M11d) — `omo run --json` 실행만(CliExecAdapter). stdout(RunResult) → raw_events 정규화.

실측: omo는 bun 런타임 필요 — 이 머신 3.11.0+bun ENOENT면 *정직하게* 비0 exit(가짜 이벤트 0). 4.7.4+bun에서
team mode 동작. Isolation: RawAgentOutput만 만든다 — 번역은 providers/omo(NAT plugin).
"""
from __future__ import annotations

import json

from ..contracts import AgentInvocation, RawAgentOutput
from .base import CliExecAdapter


def _normalize_omo(stdout: str) -> list[dict]:
    """omo run --json stdout(RunResult{success,summary}) → raw_events(kind=final). team/message 이벤트는
    event-stream 연동 시 확장(현재 omo --json은 최종 RunResult만 stdout에 준다)."""
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(result, dict) and "success" in result:
        return [{"kind": "final", "success": result.get("success"), "summary": result.get("summary", "")}]
    return []


class OmoAdapter(CliExecAdapter):
    name = "omo"
    cli = "omo"

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        return (self._base_argv()
                + ["run", invocation.prompt, "--json", "--directory", invocation.workspace_root]
                + self.extra_args)

    async def run(self, invocation: AgentInvocation) -> RawAgentOutput:
        raw = await super().run(invocation)
        raw.raw_events = _normalize_omo(raw.stdout)     # 실패(bun ENOENT)면 [] — 정직
        return raw
