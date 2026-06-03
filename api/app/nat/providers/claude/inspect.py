"""claude provider inspect (M11a) — read-only 진단. claude는 이미 NAT plugin으로 등록됨(adapter=claude)."""
from __future__ import annotations

from .. import lifecycle
from ..inspection import ProviderInspection, probe_version, runnable_blockers, which_any

_INSTALL = "claude CLI 설치 필요 — https://docs.claude.com/claude-code"


def inspect() -> ProviderInspection:
    binary = which_any(["claude"])
    hint, deps = lifecycle.install_hint_for("claude"), lifecycle.runtime_deps_for("claude")
    if not binary:
        return ProviderInspection(
            name="claude", installed=False,
            known_blockers=["claude CLI가 PATH에 없음"],
            recommended_next_action=_INSTALL,
            install_hint=hint, runtime_deps=deps)
    version = probe_version(binary)
    return ProviderInspection(
        name="claude", installed=True, binary_path=binary, version=version,
        capabilities=["nat.plugin", "subscription_default"],
        known_blockers=runnable_blockers(version),
        recommended_next_action="ready — NAT plugin 등록됨(adapter=claude)",
        install_hint=hint, runtime_deps=deps)
