"""Runner support-level labels used by doctor and harmless probes.

The support taxonomy is intentionally separate from install detection:
finding a binary on PATH does not mean Dipeen can claim the runner is supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class RunnerSupport:
    """Human-facing support claim for a provider runner."""

    level: str
    note: str


_SUPPORTED: Final[RunnerSupport] = RunnerSupport(
    level="supported",
    note="CI/e2e/doctor/docs green",
)
_PREVIEW: Final[RunnerSupport] = RunnerSupport(
    level="preview",
    note="available for explicit testing; advertise only after a healthy probe",
)
_UNKNOWN: Final[RunnerSupport] = RunnerSupport(
    level="unknown",
    note="not in the public alpha support matrix",
)

_RUNNER_SUPPORT: Final[dict[str, RunnerSupport]] = {
    "claude-code": _SUPPORTED,
    "codex": _SUPPORTED,
    "omo-opencode": _PREVIEW,
    "omo-codex-light": _PREVIEW,
    "hermes": _PREVIEW,
}


def runner_support(name: str) -> RunnerSupport:
    """Return the support claim for a runner without probing or executing it."""
    return _RUNNER_SUPPORT.get(name, _UNKNOWN)
