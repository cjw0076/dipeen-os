"""omo-codex-light 어댑터 (W2).

Codex CLI(+omo@sisyphuslabs rules/ultrawork)로 단일 태스크 실행. §7.4 시퀀스.
codex 바이너리로 직접 shell-out — 미설치 시 *정직하게* RUNNER_ERROR(완료 조작 금지).
NOTE: codex CLI의 정확한 비대화 실행 플래그는 설치본에 맞춰 검증 필요(아래는 exec 패턴).
"""
from __future__ import annotations

from .base import RunContext, RunnerHealth, run_cli_and_report, which


class OmoCodexLightAdapter:
    name = "omo-codex-light"
    install_cmd = "npm i -g @openai/codex"
    auth_cmd = "codex login   # or $env:OPENAI_API_KEY"

    async def execute(self, task: dict, ctx: RunContext) -> dict:
        codex = which("codex")
        if not codex:
            from .base import _err_result
            return _err_result(self.name, "codex 미설치",
                               ["codex CLI 미설치 — `npm i -g @openai/codex` + lazycodex 설정"])
        prompt = task.get("prompt", "")
        # 비대화 exec (`codex exec [PROMPT]`, cwd=workspace는 run_cli_and_report가 설정).
        # 팀이 준 단일 task만 실행(크로스-task delegate는 HQ가 차단).
        # NOTE: 파일 수정까지 자동 승인하려면 codex 설정/플래그(예: --full-auto, sandbox)가
        #       필요할 수 있음 — auth(`codex login`) 후 실측으로 확정.
        cmd = [codex, "exec", prompt]
        return await run_cli_and_report(cmd, task=task, ctx=ctx, runner=self.name)

    async def health(self) -> RunnerHealth:
        codex = which("codex")
        return (RunnerHealth(self.name, True, f"codex: {codex}")
                if codex else RunnerHealth(self.name, False, "codex 미설치"))
