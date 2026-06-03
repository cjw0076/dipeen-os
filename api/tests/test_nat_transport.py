"""NAT M6 — Core↔Worker 트랜스포트(pull command queue + lease + ingest).

done-when: Core가 enqueue → Worker가 poll→lease→실행(worker_execute)→업로드 → Core가 ingest+reconcile.
Core는 worker에 직접 접속 안 함(pull). command complete ≠ task done(Reconciler가 결정).
"""
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

from app.nat.contracts import TaskEnvelope, Command, WorkerInfo, _now
from app.nat.adapters.base import ExecResult
from app.nat.core import conductor, ingest
from app.nat.core.command_queue import CommandQueue
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.core.run_store import RunStore
from app.nat.worker import WorkerNode
from app.nat import providers as _providers


@pytest.fixture(autouse=True)
def _providers_ready():
    _providers.register_defaults()
    yield


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-tx-ws-"))
    for a in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
              ["git", "config", "user.name", "t"]):
        subprocess.run(a, cwd=root, check=True, capture_output=True)
    return root


def _store() -> str:
    return tempfile.mkdtemp(prefix="nat-tx-store-")


def _task(**kw) -> TaskEnvelope:
    return TaskEnvelope(title="login", intent="로그인 구현",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}], **kw)


class _FakeRunner:
    def __init__(self, result: ExecResult, *, writes=None):
        self.result, self.writes, self.calls = result, writes, []

    async def __call__(self, argv, *, cwd, env, timeout_sec):
        self.calls.append(list(argv))
        if self.writes:
            (Path(cwd) / self.writes).write_text("x\n", encoding="utf-8")
        return self.result


def _worker(store, wid="w-alice", caps=("provider.claude", "provider.codex", "workspace.write")):
    return WorkerNode(wid, capabilities=list(caps),
                      queue=CommandQueue(store), registry=WorkerRegistry(store), store_root=store)


# ════════ done-when: 전체 루프 ════════
@pytest.mark.asyncio
async def test_core_worker_full_loop_reaches_done():
    store, ws = _store(), _git_repo()
    w = _worker(store)
    w.register()
    cmd = conductor.dispatch_run(CommandQueue(store), _task(), provider="claude",
                                 workspace_root=str(ws), store_root=store)
    assert cmd.state == "queued"

    fake = _FakeRunner(ExecResult(0, "done", ""), writes="page.tsx")
    result = await w.poll_and_run_once(runner=fake)

    assert result is not None and result.state == "DONE"               # Core가 증거로 결정
    assert CommandQueue(store).get(cmd.command_id).state == "completed"  # command 완료
    assert RunStore(store).load_task(cmd.task_id).state == "DONE"        # task 영속


# ════════ pull: capability dispatch ════════
def test_poll_respects_capabilities():
    store, ws = _store(), _git_repo()
    conductor.dispatch_run(CommandQueue(store), _task(), provider="codex",
                           workspace_root=str(ws), store_root=store)
    # claude만 가진 worker는 codex command를 못 가져간다
    claude_only = CommandQueue(store).poll("w1", ["provider.claude", "workspace.write"])
    assert claude_only is None
    codex_worker = CommandQueue(store).poll("w2", ["provider.codex", "workspace.write"])
    assert codex_worker is not None and codex_worker.provider == "codex"


# ════════ lease: 중복 dispatch 방지 ════════
def test_lease_prevents_double_dispatch():
    store, ws = _store(), _git_repo()
    conductor.dispatch_run(CommandQueue(store), _task(), provider="claude",
                           workspace_root=str(ws), store_root=store)
    first = CommandQueue(store).poll("w1", ["provider.claude", "workspace.write"])
    second = CommandQueue(store).poll("w2", ["provider.claude", "workspace.write"])
    assert first is not None and second is None        # 하나의 command는 한 worker만


# ════════ lease 만료 → 재큐 ════════
def test_expired_lease_requeues():
    store, ws = _store(), _git_repo()
    conductor.dispatch_run(CommandQueue(store), _task(), provider="claude",
                           workspace_root=str(ws), store_root=store)
    q = CommandQueue(store)
    leased = q.poll("w-dead", ["provider.claude", "workspace.write"], lease_ttl_sec=300)
    assert leased is not None
    # 미래 시점(만료 후) → expire → 다시 pollable
    future = _now() + timedelta(seconds=400)
    q.expire_leases(now=future)
    again = CommandQueue(store).poll("w-fresh", ["provider.claude", "workspace.write"])
    assert again is not None and again.command_id == leased.command_id


# ════════ worker registry ════════
def test_worker_registry_register_heartbeat_online():
    store = _store()
    reg = WorkerRegistry(store)
    reg.register(WorkerInfo(worker_id="w1", capabilities=["provider.claude"]))
    assert any(w.worker_id == "w1" for w in reg.online(now=_now()))
    reg.heartbeat("w1")
    assert WorkerRegistry(store).get("w1").worker_id == "w1"
    # 오래된 heartbeat → offline
    stale = _now() + timedelta(seconds=120)
    assert all(w.worker_id != "w1" for w in WorkerRegistry(store).online(now=stale, ttl_sec=60))


# ════════ command complete ≠ task done (거짓 done) ════════
@pytest.mark.asyncio
async def test_false_done_completes_command_but_task_needs_retry():
    store, ws = _store(), _git_repo()
    w = _worker(store)
    w.register()
    cmd = conductor.dispatch_run(CommandQueue(store), _task(), provider="codex",
                                 workspace_root=str(ws), store_root=store)
    fake = _FakeRunner(ExecResult(0, "nothing", ""))                   # 변경 없음
    result = await w.poll_and_run_once(runner=fake)
    assert result.state == "NEEDS_RETRY"
    assert CommandQueue(store).get(cmd.command_id).state == "completed"  # command는 끝남
    assert RunStore(store).load_task(cmd.task_id).state == "NEEDS_RETRY"  # task는 재시도


# ════════ Isolation: Core 트랜스포트는 provider/adapter를 모른다 ════════
def test_core_transport_modules_do_not_import_providers_or_adapters():
    import app.nat.core.command_queue as cq
    import app.nat.core.worker_registry as wr
    import app.nat.core.ingest as ig
    import app.nat.core.conductor as cd
    forbidden = ("ClaudeAdapter", "CodexAdapter", "ClaudeNATPlugin", "CodexNATPlugin", "default_runner")
    for m in (cq, wr, ig, cd):
        for f in forbidden:
            assert not hasattr(m, f), f"Isolation 위반: {m.__name__} exposes {f}"
