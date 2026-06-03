"""NAT M10a — permission loop HTTP E2E (canonical store 통합 후).

approve → permission.execute command(Core 실행 X) → worker pull → executor_mode dry_run → would_execute
receipt → ledger. hard deny는 approve해도 rejected. reject는 command 없음. (acceptance #3,4,5,6,9,10,11)
"""
import tempfile
from pathlib import Path

import pytest

from app.nat.contracts import PermissionRequest, TaskEnvelope
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.command_queue import CommandQueue
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.worker import WorkerNode


def _setup(store: str, action: str, **kw) -> PermissionRequest:
    task = TaskEnvelope(title="pr", intent="make pr",
                        acceptance=[{"type": "artifact_required", "artifact_type": "pr_reference"}])
    RunStore(store).save_task(task)
    req = PermissionRequest(task_id=task.task_id, run_id="R-1", requester="agent://team/be",
                            action=action, target="github://cjw/x",
                            workspace_root=str(Path(tempfile.mkdtemp())), payload={"branch": "feat/T-1", "base": "main"}, **kw)
    PermissionLedger(store).save(req)
    return req


# ════════ approve → execute command, Core 실행 안 함 (acceptance #3,#4) ════════
@pytest.mark.asyncio
async def test_approve_enqueues_execute_command_no_core_execution(client, tmp_path, monkeypatch):
    store = str(tmp_path / "nat")
    monkeypatch.setenv("NAT_WORKSPACE", store)
    req = _setup(store, "github.pr.create")

    r = await client.post(f"/api/permissions/{req.permission_request_id}/approve")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "approved"
    assert data["command_id"] is not None             # execute command 생성됨
    assert data["executor_mode"] == "dry_run"          # 안전 기본
    # Core는 GitHub/실행 안 함 — 아직 receipt artifact 없음
    arts = (await client.get("/api/artifacts", params={"task_id": req.task_id})).json()
    assert arts == []
    # permission.execute command이 queue에 있고 worker가 가져갈 수 있음
    cmds = (await client.get("/api/commands")).json()
    assert any(c["command_type"] == "permission.execute" for c in cmds)


# ════════ worker dry_run → would_execute receipt, 실제 side effect 없음 (acceptance #5,#6,#11) ════════
@pytest.mark.asyncio
async def test_worker_dry_run_creates_would_execute_receipt(client, tmp_path, monkeypatch):
    store = str(tmp_path / "nat")
    monkeypatch.setenv("NAT_WORKSPACE", store)
    req = _setup(store, "github.pr.create")
    await client.post(f"/api/permissions/{req.permission_request_id}/approve")

    # worker가 permission.execute를 pull → 기본 dry_run
    w = WorkerNode("w-perm", capabilities=["executor.github.pr.create"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store)
    assert w.executor_mode == "dry_run"
    w.register()
    await w.drain()

    arts = ArtifactStore(store).list(task_id=req.task_id)
    assert any(a.type == "document" and any(e.kind == "would_execute" and e.passed for e in a.evidence)
               for a in arts)                          # would_execute 미리보기
    assert not any(a.type == "pr_reference" for a in arts)   # 진짜 PR receipt 없음(side effect 0)
    assert PermissionLedger(store).get(req.permission_request_id).state == "approved"   # executed 아님


# ════════ hard deny → approve해도 rejected, command 없음 (acceptance #10) ════════
@pytest.mark.asyncio
async def test_hard_deny_approve_rejects_no_command(client, tmp_path, monkeypatch):
    store = str(tmp_path / "nat")
    monkeypatch.setenv("NAT_WORKSPACE", store)
    req = _setup(store, "secret.read")
    data = (await client.post(f"/api/permissions/{req.permission_request_id}/approve")).json()
    assert data["status"] == "rejected" and data["command_id"] is None
    assert (await client.get("/api/commands")).json() == []


# ════════ reject → command 없음 (acceptance #9) ════════
@pytest.mark.asyncio
async def test_reject_permission_no_command(client, tmp_path, monkeypatch):
    store = str(tmp_path / "nat")
    monkeypatch.setenv("NAT_WORKSPACE", store)
    req = _setup(store, "github.pr.create")
    r = await client.post(f"/api/permissions/{req.permission_request_id}/reject")
    assert r.status_code == 200 and r.json()["state"] == "rejected"
    assert (await client.get("/api/commands")).json() == []


# ════════ canonical store 단일화: list가 ledger를 본다 (acceptance #1,#2) ════════
@pytest.mark.asyncio
async def test_permission_list_reads_canonical_ledger(client, tmp_path, monkeypatch):
    store = str(tmp_path / "nat")
    monkeypatch.setenv("NAT_WORKSPACE", store)
    req = _setup(store, "github.pr.create")          # PermissionLedger에 직접 저장
    perms = (await client.get("/api/permissions")).json()   # HTTP list가 같은 ledger를 봐야
    assert any(p["permission_request_id"] == req.permission_request_id for p in perms)
