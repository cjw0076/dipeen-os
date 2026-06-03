"""NAT M7 — Permission NAT (★ Core v0 게이트). agent는 요청만 / PolicyEngine 분류 / 로컬 Worker 실행.

6 acceptance(D-001): ①privileged 주장+receipt없음→¬DONE ②요청→AWAITING_PERMISSION·실행안됨 ③승인→
permission.execute command(Core 실행 아님) ④worker guard 재확인 ⑤receipt 있어야 DONE ⑥hard deny→rejected.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.nat.contracts import (
    TaskEnvelope, PermissionRequest, Artifact, ArtifactProducer, Evidence, StateClaim,
)
from app.nat.core import policy, permission_nat
from app.nat.core.reconciler import reconcile
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core.command_queue import CommandQueue
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.eventlog import EventLog
from app.nat.core.run_store import RunStore
from app.nat.executors import ExecutorResult
from app.nat.worker import WorkerNode


def _store() -> str:
    return tempfile.mkdtemp(prefix="nat-perm-")


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-perm-ws-"))
    for a in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(a, cwd=root, check=True, capture_output=True)
    return root


class _FakeExecutor:
    """주입 executor — 정해진 결과 반환(실 GitHub 호출 없이 hermetic)."""

    def __init__(self, *, success=True, uri="github://cjw/x/pull/12"):
        self.success, self.uri, self.calls = success, uri, []

    def execute(self, action, target, payload):
        self.calls.append((action, target, dict(payload)))
        return ExecutorResult(success=self.success, uri=self.uri,
                              message="ok" if self.success else "failed")


def _pr_req(store, *, task_id="T-1", workspace_root="", payload=None) -> PermissionRequest:
    return PermissionRequest(task_id=task_id, run_id="R-1", requester="agent://team/backend",
                             action="github.pr.create", target="github://cjw/x", worker_id="w1",
                             workspace_root=workspace_root,
                             payload=payload or {"branch": "feat/T-1", "base": "main"})


# ════════ PolicyEngine 분류 ════════
def test_policy_classify_by_risk_class():
    assert policy.classify("secret.read") == "deny"
    assert policy.classify("deployment.run") == "deny"
    assert policy.classify("shell.run") == "deny"
    assert policy.classify("github.pr.create") == "require_human_approval"
    assert policy.classify("git.push") == "require_human_approval"
    assert policy.classify("workspace.write") == "auto_allow"
    assert policy.classify("git.diff") == "auto_allow"


# ════════ Test 6 — Hard deny ════════
def test_hard_deny_rejects_without_command():
    store = _store()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    req = PermissionRequest(task_id="T-1", run_id="R-1", requester="agent://team/be", action="secret.read")
    out = permission_nat.submit_request(req, ledger=ledger, queue=queue, store_root=store)
    assert out.policy_decision == "deny" and out.state == "rejected"
    assert queue._all() == []                                    # command 없음
    assert "permission.rejected" in {e.event_type for e in EventLog(store).read_all()}  # audit


# ════════ Test 2 — 요청이 상태를 막음 ════════
def test_request_blocks_task_state_no_execute_command():
    store = _store()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    out = permission_nat.submit_request(_pr_req(store), ledger=ledger, queue=queue, store_root=store)
    assert out.policy_decision == "require_human_approval" and out.state == "requested"
    task = TaskEnvelope(title="pr", intent="i",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    r = reconcile(task, claims=[], artifacts=[], permissions=[out])
    assert r.state == "AWAITING_PERMISSION"
    assert queue._all() == []                                    # 승인 전 execute command 없음


# ════════ Test 3 — 승인은 worker command, Core 실행 아님 ════════
def test_approval_enqueues_execute_command_not_core_execution():
    store = _store()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    req = _pr_req(store)
    permission_nat.submit_request(req, ledger=ledger, queue=queue, store_root=store)
    cmd = permission_nat.approve(req.permission_request_id, decider="user://cjw", ledger=ledger, queue=queue)
    assert cmd is not None and cmd.command_type == "permission.execute"
    assert cmd.permission_id == req.permission_request_id
    assert cmd.required_capabilities == ["executor.github.pr.create"]
    assert ledger.get(req.permission_request_id).state == "approved"
    assert ArtifactStore(store).list(task_id="T-1") == []        # Core가 실행 안 함(receipt 없음)
    assert "permission.approved" in {e.event_type for e in EventLog(store).read_all()}


# ════════ Test 1 — privileged 주장 + receipt 없음 → ¬DONE ════════
def test_privileged_claim_without_receipt_not_done():
    task = TaskEnvelope(title="pr task", intent="i",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    code = Artifact(type="code_patch", task_id=task.task_id, run_id="R-1",
                    producer=ArtifactProducer(identity="a", adapter="claude"),
                    evidence=[Evidence(kind="git_diff_exists", passed=True)])
    claim = StateClaim(task_id=task.task_id, run_id="R-1", producer="a", claimed_state="done")
    r = reconcile(task, claims=[claim], artifacts=[code])
    assert r.state == "NEEDS_RETRY"                              # pr_reference receipt 없음 → 거짓 done


# ════════ Test 5 — receipt 있어야 DONE (전체 플로우) ════════
@pytest.mark.asyncio
async def test_full_flow_receipt_yields_done():
    store, ws = _store(), _git_repo()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    task = TaskEnvelope(title="pr", intent="make pr",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    RunStore(store).save_task(task)
    req = _pr_req(store, task_id=task.task_id, workspace_root=str(ws))
    permission_nat.submit_request(req, ledger=ledger, queue=queue, store_root=store)
    permission_nat.approve(req.permission_request_id, decider="user://cjw", ledger=ledger, queue=queue)

    w = WorkerNode("w1", capabilities=["executor.github.pr.create"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store,
                   executors={"github.pr.create": _FakeExecutor(success=True)},
                   executor_mode="local_execute")              # 실제 실행 명시(기본은 dry_run)
    result = await w.poll_and_run_once()
    assert result.state == "DONE"
    arts = ArtifactStore(store).list(task_id=task.task_id)
    assert any(a.type == "pr_reference" and a.status == "verified" for a in arts)
    assert PermissionLedger(store).get(req.permission_request_id).state == "executed"


# ════════ Test 4 — worker local guard 재확인 → 거부 ════════
@pytest.mark.asyncio
async def test_worker_guard_rejects_invalid_base():
    store, ws = _store(), _git_repo()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    task = TaskEnvelope(title="pr", intent="i",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    RunStore(store).save_task(task)
    req = _pr_req(store, task_id=task.task_id, workspace_root=str(ws),
                  payload={"branch": "feat/T-1", "base": "prod-secret"})   # invalid base
    permission_nat.submit_request(req, ledger=ledger, queue=queue, store_root=store)
    permission_nat.approve(req.permission_request_id, decider="user://cjw", ledger=ledger, queue=queue)

    fake = _FakeExecutor(success=True)
    w = WorkerNode("w1", capabilities=["executor.github.pr.create"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store,
                   executors={"github.pr.create": fake})
    result = await w.poll_and_run_once()
    assert result.state != "DONE"                               # guard가 막음
    assert fake.calls == []                                     # executor 호출 안 됨
    arts = ArtifactStore(store).list(task_id=task.task_id)
    assert any(a.type == "pr_reference" and a.status == "rejected" for a in arts)  # 실패 receipt


# ════════ executor_mode 안전 기본값(dry_run) — 승인만으로 진짜 side effect 없음 ════════
@pytest.mark.asyncio
async def test_dry_run_default_does_not_execute_or_complete():
    store, ws = _store(), _git_repo()
    ledger, queue = PermissionLedger(store), CommandQueue(store)
    task = TaskEnvelope(title="pr", intent="i",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    RunStore(store).save_task(task)
    req = _pr_req(store, task_id=task.task_id, workspace_root=str(ws))
    permission_nat.submit_request(req, ledger=ledger, queue=queue, store_root=store)
    permission_nat.approve(req.permission_request_id, decider="user://cjw", ledger=ledger, queue=queue)
    fake = _FakeExecutor(success=True)
    w = WorkerNode("w1", capabilities=["executor.github.pr.create"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store,
                   executors={"github.pr.create": fake})         # executor_mode 미지정 → 기본 dry_run
    assert w.executor_mode in ("dry_run", "manual_handoff")      # 기본은 안전(local_execute 아님)
    result = await w.poll_and_run_once()
    assert result.state != "DONE"                                # dry_run은 task 완료 X
    assert fake.calls == []                                      # 진짜 executor 호출 X(side effect 없음)
    arts = ArtifactStore(store).list(task_id=task.task_id)
    assert any(a.type == "document" and any(e.kind == "would_execute" for e in a.evidence) for a in arts)


# ════════ Isolation: Core permission 모듈은 executor/adapter를 모른다 ════════
def test_core_permission_modules_do_not_import_executors_or_adapters():
    import app.nat.core.policy as pol
    import app.nat.core.permission_ledger as pl
    import app.nat.core.permission_nat as pn
    forbidden = ("ExecutorPlugin", "guard_check", "ClaudeAdapter", "CodexAdapter", "WorkerNode")
    for m in (pol, pl, pn):
        for f in forbidden:
            assert not hasattr(m, f), f"Isolation 위반: {m.__name__} exposes {f}"
