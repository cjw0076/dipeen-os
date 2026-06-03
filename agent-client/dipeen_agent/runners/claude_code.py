"""claude-code 어댑터 (W0 기본).

기존 runtime._execute_subprocess(풍부한 경로: cancel·question·PR·promise)를 그대로 재사용 →
동작 불변. build_cli_cmd가 claude/opencode CLI를 선택한다. health는 바이너리 존재 확인.
"""
from __future__ import annotations

from .base import RunContext, RunnerHealth, which


class ClaudeCodeAdapter:
    name = "claude-code"
    install_cmd = "npm i -g @anthropic-ai/claude-code   # or opencode"
    auth_cmd = "claude   # subscription OAuth, or claude /login"

    async def execute(self, task: dict, ctx: RunContext) -> dict:
        return await ctx.runtime._execute_subprocess(task)

    async def health(self) -> RunnerHealth:
        if which("claude"):
            return RunnerHealth(self.name, True, "claude CLI 발견")
        try:
            from ..config import find_opencode_exe
            exe = find_opencode_exe()
        except Exception:
            exe = None
        if exe:
            return RunnerHealth(self.name, True, f"opencode: {exe}")
        return RunnerHealth(self.name, False,
                            "claude/opencode 없음 — `npm i -g @anthropic-ai/claude-code` 또는 opencode 설치")
