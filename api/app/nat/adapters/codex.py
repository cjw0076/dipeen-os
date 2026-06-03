"""CodexAdapter (M2) — codex CLI 비대화 실행만(`codex exec PROMPT`).

파일수정 자동승인 플래그(--full-auto/sandbox 등)는 설치본에 따라 다르므로 M5(CLI) 실측에서 확정.
어댑터는 artifact/state를 만들지 않는다 — RawAgentOutput만(§10 Isolation).
"""
from __future__ import annotations

from ..contracts import AgentInvocation
from .base import CliExecAdapter


class CodexAdapter(CliExecAdapter):
    name = "codex"
    cli = "codex"

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        # codex exec [extra…] <prompt>. extra_args=권한/샌드박스 우회(예: --dangerously-bypass-approvals-and-sandbox)
        return self._base_argv() + ["exec"] + self.extra_args + [invocation.prompt]
