"""NAT providers (M3+) — provider별 번역 플러그인. Core는 여기를 import하지 않고 registry로만 접근.

`register_defaults()`가 claude/codex를 registry에 등록한다(멱등). 앱 시작/CLI/테스트가 1회 호출하면
이후 Core의 outbound/inbound가 이름으로 위임할 수 있다. import 시에도 자동 등록(side-effect).
"""
from __future__ import annotations

from ..core import registry
from .claude import ClaudeNATPlugin
from .codex import CodexNATPlugin
from .fake import FakeNATPlugin
from .hermes import HermesNATPlugin
from .omo import OmoNATPlugin


def register_defaults() -> None:
    """기본 provider(claude/codex/fake/omo/hermes) 등록. 멱등 — 여러 번 호출해도 안전.
    fake=키 없는 결정론 provider(데모/CI). omo/hermes=M11c–e(team/memory). 등록만으론 안전 — worker가
    provider.X capability를 가져야 lease(Provider Lifecycle: probe healthy 시에만 광고)."""
    registry.register_plugin(ClaudeNATPlugin())
    registry.register_plugin(CodexNATPlugin())
    registry.register_plugin(FakeNATPlugin())
    registry.register_plugin(OmoNATPlugin())
    registry.register_plugin(HermesNATPlugin())


register_defaults()        # import 시 자동 등록

__all__ = ["register_defaults", "ClaudeNATPlugin", "CodexNATPlugin", "FakeNATPlugin",
           "OmoNATPlugin", "HermesNATPlugin"]
