"""ProviderNAT registry (M3 / §15) — Core가 provider를 *이름으로* 위임하는 지점.

원칙(Isolation): Dipeen Core(outbound/inbound)는 ClaudeNATPlugin/CodexNATPlugin을 직접 import하지 않는다.
provider 모듈이 자신을 registry에 등록(side-effect)하고, Core는 `get_plugin(name)`으로만 접근 →
Conductor/NAT에 `if provider == "claude"` 같은 분기 0건.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..contracts import (
    AgentInvocation, Artifact, Event, RawAgentOutput, StateClaim, TaskEnvelope,
)


@runtime_checkable
class ProviderNATPlugin(Protocol):
    """provider별 NAT 번역기. Outbound 1메서드 + Inbound 3메서드(M3). permission/memory는 M5/M7.

    Core는 이 Protocol만 알고 구현체(claude/codex/omo/…)는 모른다.
    """
    name: str

    def to_invocation(self, task: TaskEnvelope, *, run_id: str, identity_id: str,
                      workspace_root: str, context_pack: Optional[str] = None) -> AgentInvocation: ...

    def parse_artifacts(self, raw: RawAgentOutput, *, task_id: str) -> list[Artifact]: ...
    def parse_state_claims(self, raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]: ...
    def parse_events(self, raw: RawAgentOutput, *, task_id: str,
                     artifacts: list[Artifact]) -> list[Event]: ...


_REGISTRY: dict[str, ProviderNATPlugin] = {}


def register_plugin(plugin: ProviderNATPlugin) -> None:
    """provider 플러그인 등록(이름 기준, 멱등 — 재등록은 덮어씀)."""
    _REGISTRY[plugin.name] = plugin


def get_plugin(name: str) -> ProviderNATPlugin:
    """이름으로 플러그인 조회. 미등록이면 KeyError(정직한 실패 — provider 누락을 숨기지 않음)."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"NAT provider 미등록: {name!r} (등록됨: {sorted(_REGISTRY)})")


def registered() -> list[str]:
    return sorted(_REGISTRY)


def clear() -> None:
    """테스트 격리용."""
    _REGISTRY.clear()
