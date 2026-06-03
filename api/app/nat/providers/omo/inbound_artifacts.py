"""OMO inbound artifacts (M11e) — review → review_result, diff → code_patch (독립 파서)."""
from __future__ import annotations

from ...contracts import Artifact, ArtifactProducer, Evidence, RawAgentOutput


def omo_artifacts(raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
    out: list[Artifact] = []
    producer = ArtifactProducer(identity=raw.identity_id or "agent://team/omo", adapter="omo")
    for ev in raw.raw_events:
        if ev.get("kind") == "review":                # team review loop 산출 → review_result
            out.append(Artifact(
                type="review_result", task_id=task_id, run_id=raw.run_id, producer=producer,
                title=f"omo review: {ev.get('verdict', '')}",
                summary=str(ev.get("content", ""))[:500],
                evidence=[Evidence(kind="omo_review", passed=ev.get("verdict") == "approved",
                                   message=str(ev.get("verdict", "")))]))
    if raw.changed_files:                              # 실제 만진 파일 → code_patch
        out.append(Artifact(
            type="code_patch", task_id=task_id, run_id=raw.run_id, producer=producer,
            summary=f"{len(raw.changed_files)} files changed",
            evidence=[Evidence(kind="git_diff_exists", passed=True)]))
    return out
