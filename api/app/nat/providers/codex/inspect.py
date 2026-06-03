"""codex provider inspect (M11a) — read-only 진단. codex는 이미 NAT plugin으로 등록됨(adapter=codex)."""
from __future__ import annotations

from .. import lifecycle
from ..inspection import ProviderInspection, probe_version, runnable_blockers, which_any

_INSTALL = "codex CLI 설치 필요 — `npm i -g @openai/codex` (또는 배포본)"


def inspect() -> ProviderInspection:
    binary = which_any(["codex"])
    hint, deps = lifecycle.install_hint_for("codex"), lifecycle.runtime_deps_for("codex")
    if not binary:
        return ProviderInspection(
            name="codex", installed=False,
            known_blockers=["codex CLI가 PATH에 없음"],
            recommended_next_action=_INSTALL,
            install_hint=hint, runtime_deps=deps)
    version = probe_version(binary)
    return ProviderInspection(
        name="codex", installed=True, binary_path=binary, version=version,
        capabilities=["nat.plugin"],
        known_blockers=runnable_blockers(version),
        recommended_next_action="ready — NAT plugin 등록됨(adapter=codex)",
        install_hint=hint, runtime_deps=deps)
