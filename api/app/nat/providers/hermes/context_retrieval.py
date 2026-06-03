"""Hermes inbound — memory retrieval(session/semantic search) → context_evidence Artifact.

hermes는 과거 세션/메모리를 검색해 컨텍스트를 끌어온다(prefetch/semantic_search). 그 검색 결과를
context_evidence Artifact로 — agent가 *무엇을 근거로* 행동했는지의 증거(Evidence First).
"""
from __future__ import annotations

from ...contracts import Artifact, ArtifactProducer, Evidence, RawAgentOutput


def context_evidence_artifacts(raw: RawAgentOutput, *, task_id: str) -> list[Artifact]:
    out: list[Artifact] = []
    producer = ArtifactProducer(identity=raw.identity_id or "agent://team/hermes", adapter="hermes")
    for ev in raw.raw_events:
        if ev.get("kind") == "retrieval":
            results = ev.get("results") or []
            out.append(Artifact(
                type="context_evidence", task_id=task_id, run_id=raw.run_id, producer=producer,
                title=f"hermes retrieval: {str(ev.get('query', ''))[:60]}",
                summary=f"{len(results)} results",
                evidence=[Evidence(kind="hermes_retrieval", passed=bool(results),
                                   message="; ".join(str(r) for r in results)[:300])]))
    return out
