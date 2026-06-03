"""provider.fake — 키 없는 결정론적 provider (BYOK 데모 마찰의 답, Gate5 키스톤).

CLI/네트워크/API 키 0. 실행 = 워크스페이스에 결정론적 파일 1개 작성 → **진짜** git diff → code_patch.
공개 데모 참가자가 키 없이 전 루프(실행→증거→검증→reconcile)를 본다.

번역(to_invocation/parse_*)은 provider-불가지(changed_files→code_patch)라 ClaudeNATPlugin과 동일 → 상속 재사용.
다른 것은 *실행*뿐: FakeAdapter는 CLI를 켜지 않고 직접 RawAgentOutput을 만든다.
"""
from __future__ import annotations

from pathlib import Path

from ...adapters.base import detect_changed_files
from ...contracts import AgentInvocation, RawAgentOutput
from ..claude import ClaudeNATPlugin


class FakeAdapter:
    """CLI를 켜지 않는 결정론적 어댑터. `_adapter_for` 호환 시그니처(runner/extra_args 무시)."""

    def __init__(self, runner=None, extra_args=None) -> None:
        pass

    async def run(self, invocation: AgentInvocation) -> RawAgentOutput:
        ws = Path(invocation.workspace_root or ".")
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "dipeen_fake_change.txt").write_text(
            "# dipeen fake provider (keyless demo)\n"
            f"# intent: {(invocation.prompt or '')[:160]}\n"
            "implemented = True\n",
            encoding="utf-8")
        changed = detect_changed_files(str(ws)) or ["dipeen_fake_change.txt"]
        return RawAgentOutput(
            run_id=invocation.run_id, identity_id=invocation.identity_id, exit_code=0,
            stdout="[fake] deterministic change written — no key, no network, no CLI.",
            stderr="", changed_files=changed, workspace_root=str(ws))


class FakeNATPlugin(ClaudeNATPlugin):
    """fake = claude와 동일 번역 + name만 다름(실행만 FakeAdapter가 다름)."""
    name = "fake"


__all__ = ["FakeNATPlugin", "FakeAdapter"]
