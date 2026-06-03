"""Hermes inbound artifacts (M11e) — context_evidence(retrieval) 종합. plugin.parse_artifacts가 위임."""
from __future__ import annotations

from ...contracts import Artifact, RawAgentOutput
from .context_retrieval import context_evidence_artifacts


def hermes_artifacts(raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
    return context_evidence_artifacts(raw, task_id=task_id)
