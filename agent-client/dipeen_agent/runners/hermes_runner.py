"""hermes-runner 어댑터 (W6).

hermes CLI를 비대화 single-shot(--no-gateway)으로 실행. §7.4 hermes 시퀀스.
팀 task/memory는 HQ가 소유 — hermes 로컬 MEMORY는 노드 한정(profile 격리는 운영 정책).
미설치 시 정직하게 RUNNER_ERROR.
NOTE: hermes CLI의 정확한 비대화 플래그는 설치본에 맞춰 검증 필요(아래는 run 패턴).
"""
from __future__ import annotations

from .base import RunContext, RunnerHealth, run_cli_and_report, which


class HermesRunnerAdapter:
    name = "hermes"
    install_cmd = "uv tool install --python 3.11 git+https://github.com/NousResearch/hermes-agent"
    auth_cmd = "hermes model   # provider/model 선택(interactive, TTY) — Nous Portal/OpenRouter/OpenAI 등"

    async def execute(self, task: dict, ctx: RunContext) -> dict:
        hermes = which("hermes")
        if not hermes:
            from .base import _err_result
            return _err_result(self.name, "hermes 미설치", ["hermes CLI 미설치"])
        prompt = task.get("prompt", "")
        cmd = [hermes, "run", "--no-gateway", "--prompt", prompt]
        return await run_cli_and_report(cmd, task=task, ctx=ctx, runner=self.name)

    async def health(self) -> RunnerHealth:
        hermes = which("hermes")
        return (RunnerHealth(self.name, True, f"hermes: {hermes}")
                if hermes else RunnerHealth(self.name, False, "hermes 미설치"))
