"""Runner support-level labels shown by onboarding surfaces.

This keeps "binary was found" separate from "Dipeen can safely route work here".
The policy matches docs/SUPPORT_LEVELS.md: installed/probed/advertised/supported
are different claims.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunnerSupport:
    level: str
    note: str


_SUPPORT: dict[str, RunnerSupport] = {
    "claude": RunnerSupport("supported", "primary provider path; still requires local auth/BYOK"),
    "codex": RunnerSupport("supported", "primary provider path; still requires local auth/BYOK"),
    "claude-code": RunnerSupport("supported", "primary worker path; still requires local auth/BYOK"),
    "omo-codex-light": RunnerSupport("preview", "Codex CLI wrapper; advertise only after live probe evidence"),
    "omo-opencode": RunnerSupport("preview", "OMO/OpenCode path; advertise only after live probe evidence"),
    "hermes": RunnerSupport("preview", "Hermes local-memory path; advertise only after live probe evidence"),
}


def runner_support(name: str) -> RunnerSupport:
    return _SUPPORT.get(name, RunnerSupport("preview", "unknown runner; do not advertise without a probe"))
