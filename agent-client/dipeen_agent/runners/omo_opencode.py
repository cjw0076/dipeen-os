"""omo-opencode 어댑터 (W5).

AGENT_EXECUTOR=omo일 때 config.build_cli_cmd가 `omo run --directory <ws> ... --json`을
구성하므로, 기존 subprocess 경로를 재사용한다(동작 불변). delegate_task/call_omo_agent는
어댑터 *밖*(HQ)에서만 — PM이 tasks row를 여러 개 만드는 것으로 팀 서브에이전트 표현(§7.4).
health는 omo/opencode 바이너리 확인.
"""
from __future__ import annotations

from .base import RunContext, RunnerHealth, which


class OmoOpencodeAdapter:
    name = "omo-opencode"
    install_cmd = "bunx oh-my-openagent install"   # OpenCode Ultimate · ⚠️ global npm/`npx omo`/`bunx omo` 금지
    auth_cmd = "opencode auth login   # + AGENT_EXECUTOR=omo"
    runtime_deps = ["bun"]                 # opencode는 bun 런타임 필요(M11a inspect가 ENOENT 적발)

    async def execute(self, task: dict, ctx: RunContext) -> dict:
        return await ctx.runtime._execute_subprocess(task)

    async def health(self) -> RunnerHealth:
        exe = which("omo") or which("opencode")
        if exe:
            return RunnerHealth(self.name, True, f"omo/opencode: {exe}")
        return RunnerHealth(self.name, False,
                            "omo 미설치 — opencode + OhMyOpenCodePlugin 필요(study-guide §3)")
