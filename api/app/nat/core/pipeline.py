"""NAT M5 — in-process 파이프라인 (실측 증명 + 미래 Worker Command Executor 코어).

outbound → adapter.run → inbound → verify/reconcile → persist. 한 프로세스로 M1~M4를 실측 검증한다.
**worker_execute(Worker측: 실행+번역) / core_reconcile(Core측: 판단+기록)** 솔기 = M6 Core↔Worker 분리점.

주의(두 평면): 이 코드는 *빌드타임* 구현물. runner=None으로 돌리면 *런타임* provider(별개 claude/codex
인스턴스)를 샌드박스에서 실행한다 — 그 agent는 개발자(나)도 Dipeen Core도 아닌, 격리 대상.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..contracts import (
    AgentBinding, AgentIdentity, AgentInvocation, Event, FailureType,
    NormalizedAgentResult, RawAgentOutput, Run, TaskEnvelope, TaskState,
)
from ..adapters.base import CommandRunner
from ..adapters.claude import ClaudeAdapter
from ..adapters.codex import CodexAdapter
from ..adapters.hermes import HermesAdapter
from ..adapters.omo import OmoAdapter
from ..providers.fake import FakeAdapter   # 키 없는 결정론 실행기(데모/CI) — CLI 안 켬
from . import inbound, outbound
from .artifact_store import ArtifactStore
from .eventlog import EventLog
from .ingest import ingest_result
from .reconciler import ReconcileResult
from .run_store import RunStore

# provider명 → 실행 어댑터(Worker가 가진 provider 풀). NAT 번역 플러그인과는 별개(registry).
_ADAPTERS = {"claude": ClaudeAdapter, "codex": CodexAdapter, "fake": FakeAdapter,
             "omo": OmoAdapter, "hermes": HermesAdapter}

# 실측 headless 권한우회 — *스크래치 워크스페이스 전용*. M7 Permission NAT가 정식 대체.
_BYPASS = {
    "claude": ["--dangerously-skip-permissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
}


def _adapter_for(provider: str, runner: Optional[CommandRunner], *, bypass: bool):
    cls = _ADAPTERS[provider]
    return cls(runner=runner, extra_args=(_BYPASS.get(provider, []) if bypass else []))


@dataclass
class RunOutcome:
    task: TaskEnvelope
    run: Run
    invocation: AgentInvocation
    raw: RawAgentOutput
    normalized: NormalizedAgentResult
    state: TaskState
    failure_type: Optional[FailureType] = None
    reasons: list[str] = field(default_factory=list)


async def worker_execute(task: TaskEnvelope, identity: AgentIdentity, *, run_id: str,
                         workspace_root: str, runner: Optional[CommandRunner] = None,
                         bypass: bool = False, timeout_sec: Optional[int] = None,
                         worker_id: Optional[str] = None):
    """[Worker 측] outbound→adapter.run(provider 실행)→inbound. M6에서 이 부분이 노드로 분리된다.
    worker_id는 *실행 노드*가 RunReport(raw)에 찍는다 — adapter는 자기가 어느 worker인지 모른다."""
    inv = outbound.build_invocation(task, identity, run_id=run_id, workspace_root=workspace_root)
    if timeout_sec:                                  # 실측 행 방지(고아 자식 차단)
        inv = inv.model_copy(update={"timeout_sec": timeout_sec})
    adapter = _adapter_for(identity.binding.adapter, runner, bypass=bypass)
    raw = await adapter.run(inv)
    if worker_id:
        raw.worker_id = worker_id                    # 실행 노드 식별(어느 머신에서 돌았나)
    normalized = inbound.normalize(raw, provider=identity.binding.adapter, task_id=task.task_id)
    return inv, raw, normalized


def core_reconcile(task: TaskEnvelope, run: Run, normalized: NormalizedAgentResult, *,
                   store_root: str) -> ReconcileResult:
    """[Core 측] M6 `ingest_result`로 위임(어댑터 비의존, Worker가 HTTP로 올려도 동일). worker_execute의 짝."""
    return ingest_result(task, run_id=run.run_id, normalized=normalized, store_root=store_root)


async def run_task(intent: str, *, provider: str, workspace_root: str, store_root: str,
                   title: Optional[str] = None, acceptance: Optional[list] = None,
                   runner: Optional[CommandRunner] = None, bypass: bool = False,
                   timeout_sec: Optional[int] = None) -> RunOutcome:
    """전체 in-process 파이프라인. runner=None이면 실측 default_runner로 진짜 provider 실행."""
    task = TaskEnvelope(title=title or intent[:48], intent=intent, acceptance=acceptance or [])
    identity = AgentIdentity(identity_id=f"agent://team/{provider}", role=provider,
                             binding=AgentBinding(adapter=provider))
    rs = RunStore(store_root)
    rs.save_task(task)
    run = Run(task_id=task.task_id, identity_id=identity.identity_id,
              attempt=rs.next_attempt(task.task_id))
    rs.save_run(run)
    inv, raw, normalized = await worker_execute(
        task, identity, run_id=run.run_id, workspace_root=workspace_root,
        runner=runner, bypass=bypass, timeout_sec=timeout_sec)
    result = core_reconcile(task, run, normalized, store_root=store_root)
    return RunOutcome(task=task, run=run, invocation=inv, raw=raw, normalized=normalized,
                      state=result.state, failure_type=result.failure_type, reasons=result.reasons)


def inspect_task(task_id: str, *, store_root: str) -> dict:
    """task의 구조화 뷰 — runs/artifacts/events/state. CLI inspect가 출력(에이전트 무관 동일 구조)."""
    rs, store, log = RunStore(store_root), ArtifactStore(store_root), EventLog(store_root)
    task = rs.load_task(task_id)
    return {
        "task_id": task_id,
        "title": task.title if task else None,
        "intent": task.intent if task else None,
        "state": task.state if task else None,
        "runs": [{"run_id": r.run_id, "identity": r.identity_id, "attempt": r.attempt}
                 for r in rs.runs_for(task_id)],
        "artifacts": [{"id": a.artifact_id, "type": a.type, "status": a.status,
                       "summary": a.summary, "evidence": [(e.kind, e.passed) for e in a.evidence]}
                      for a in store.list(task_id=task_id)],
        "events": [(e.event_type, e.message) for e in log.by_task(task_id)],
    }
