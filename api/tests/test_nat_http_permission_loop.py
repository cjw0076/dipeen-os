"""NAT (가) — HTTP permission 루프 E2E: 원격 worker가 승인된 permission.execute를 pull해 dry_run receipt POST.

approve(HTTP) → permission.execute command queued → WorkerHttpClient.poll_once → 로컬 receipt 계산
→ permission-result POST → Core가 receipt artifact 영속 + ledger 갱신 + command 완료.

**Core는 실행하지 않는다.** 기본 dry_run: would_execute 미리보기만(진짜 PR/push 없음).
"""
import pytest

from app.nat.contracts import PermissionRequest, TaskEnvelope
from app.nat.core.command_queue import CommandQueue
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core.run_store import RunStore
from app.nat.worker_http import WorkerHttpClient


def _seed_requested_permission(store: str, *, action: str = "github.pr.create") -> tuple[TaskEnvelope, PermissionRequest]:
    task = TaskEnvelope(title="ship", intent="PR 올리기")
    RunStore(store).save_task(task)
    req = PermissionRequest(
        task_id=task.task_id, run_id="R-perm-1", requester="agent://team/be",
        action=action, target="feature/login", reason="PR 생성 승인 요청",
        risk="medium", requires_human_approval=True,
        workspace_root=str(store), payload={"branch": "feature/login", "base": "main"},
    )
    PermissionLedger(store).save(req)
    return task, req


@pytest.mark.asyncio
async def test_http_worker_permission_execute_dry_run_receipt(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))      # 서버/테스트 같은 store
    monkeypatch.setenv("DIPEEN_PERMISSION_EXECUTOR_MODE", "dry_run")
    store = str(tmp_path / "nat")
    task, req = _seed_requested_permission(store)

    # 사람 승인(HTTP) → side-effect action이라 permission.execute command enqueue
    r = await client.post(f"/api/permissions/{req.permission_request_id}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["executor_mode"] == "dry_run"
    cmd_id = body["command_id"]
    assert cmd_id, "executable action이면 command_id가 있어야 함"

    # 원격 worker(executor capability 보유)가 permission.execute를 pull → dry_run receipt POST
    w = WorkerHttpClient("w-exec", ["executor.github.pr.create"], http=client)
    await w.register()
    assert await w.poll_once() is True
    assert await w.poll_once() is False                            # 빈 큐

    # receipt artifact 영속 확인(dry_run → document + would_execute, side effect 없음)
    arts = (await client.get("/api/artifacts", params={"task_id": task.task_id})).json()
    receipts = [a for a in arts if "receipt" in a["title"]]
    assert receipts, "permission receipt artifact가 영속되어야 함"
    assert receipts[0]["type"] == "document"
    assert any(e["kind"] == "would_execute" for e in receipts[0]["evidence"])

    # ledger: dry_run은 실행 안 했으므로 approved(executed 아님)
    assert PermissionLedger(store).get(req.permission_request_id).state == "approved"
    # command 완료
    assert CommandQueue(store).get(cmd_id).state == "completed"


@pytest.mark.asyncio
async def test_http_worker_permission_execute_guard_reject_no_side_effect(client, tmp_path, monkeypatch):
    """local_execute라도 guard가 거부하면(예: main 직접 push) receipt는 실패 증거 — side effect 없음."""
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    monkeypatch.setenv("DIPEEN_PERMISSION_EXECUTOR_MODE", "local_execute")
    store = str(tmp_path / "nat")
    task = TaskEnvelope(title="push", intent="main push")
    RunStore(store).save_task(task)
    req = PermissionRequest(
        task_id=task.task_id, run_id="R-perm-2", requester="agent://team/be", action="git.push",
        target="main", reason="push", risk="high", requires_human_approval=True,
        workspace_root=str(store), payload={"branch": "main"},      # main 직접 push → guard 거부
    )
    PermissionLedger(store).save(req)

    body = (await client.post(f"/api/permissions/{req.permission_request_id}/approve")).json()
    cmd_id = body["command_id"]
    assert cmd_id

    w = WorkerHttpClient("w-exec", ["executor.git.push"], http=client)
    await w.register()
    assert await w.poll_once() is True

    arts = (await client.get("/api/artifacts", params={"task_id": task.task_id})).json()
    receipts = [a for a in arts if "receipt" in a["title"]]
    assert receipts
    assert any(e["kind"] == "executor_success" and e["passed"] is False
               for e in receipts[0]["evidence"]), "guard 거부는 executor_success=False 증거"
    assert CommandQueue(store).get(cmd_id).state == "completed"
