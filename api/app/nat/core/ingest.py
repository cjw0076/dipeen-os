"""Ingest (M6 / Core 측) — Worker가 업로드한 NormalizedAgentResult를 영속 + verify/reconcile → TaskState.

Core는 provider/adapter를 모른다(번역·실행은 Worker). 여기선 *증거로* 조직 상태만 결정·기록한다.
M5 pipeline.core_reconcile의 로직을 Core 전용(어댑터 비의존)으로 분리 — Worker가 HTTP로 올려도 동일.
"""
from __future__ import annotations

from ..contracts import Event, NormalizedAgentResult, TaskEnvelope
from .artifact_store import ArtifactStore
from .eventlog import EventLog
from .reconciler import ReconcileResult, reconcile
from .run_store import RunStore


def ingest_result(task: TaskEnvelope, *, run_id: str, normalized: NormalizedAgentResult,
                  store_root: str) -> ReconcileResult:
    """events append + verified artifact save + reconcile(증거→TaskState) + task state 영속."""
    result = reconcile(task, claims=normalized.state_claims, artifacts=normalized.artifacts)
    log, store, rs = EventLog(store_root), ArtifactStore(store_root), RunStore(store_root)
    log.append_all(normalized.events)
    for a in result.artifacts:
        store.save(a)
    rs.update_task_state(task.task_id, result.state)
    log.append(Event(event_type="state.reconciled", task_id=task.task_id, run_id=run_id,
                     producer="dipeen://core", message=result.state))
    return result
