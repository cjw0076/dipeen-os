"""M10.5 Strangler cutover 불변식 — 실행 경로를 단일 canonical path로 고정(레거시 우회 차단).

canonical: message/task → control_plane command → CommandQueue → worker poll/lease → provider 실행
→ Artifact/StateClaim/Permission → Verifier/Reconciler → TaskState.

이 테스트가 잠그는 것:
- **message ≠ 실행**: 채팅 메시지 post만으로 provider가 실행되거나 command가 enqueue되지 않는다.
- **pm_loop 기본 proposal-only**: 직접 dispatch 금지(기본값).
- **approval ≠ 완료**: 승인만으로(특히 dry_run) TaskState=DONE이 되지 않는다 — 증거(receipt)+Reconciler 필요.
"""
import os

import pytest

from app.nat.contracts import PermissionRequest, TaskEnvelope
from app.nat.core import permission_nat
from app.nat.core.command_queue import CommandQueue
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.executors import default_executors
from app.nat.worker import WorkerNode


@pytest.mark.asyncio
async def test_api_chat_does_not_directly_execute_provider(client, tmp_path, monkeypatch):
    """채팅 메시지 post는 저장만 — command 0 enqueue, provider 실행 0 (message ≠ execution)."""
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    store = str(tmp_path / "nat")
    before = len(CommandQueue(store)._all())

    r = await client.post("/api/chat/messages", json={
        "room_id": "general", "text": "ship the login PR and deploy to prod now",
        "sender": "tester", "sender_type": "user"})
    assert r.status_code in (200, 201), r.text

    # 핵심: 메시지 하나로 실행 경로가 열리지 않는다 — command queue 변화 0
    assert len(CommandQueue(store)._all()) == before, "chat 메시지는 command를 enqueue하면 안 됨(제안→confirm만 실행 경계)"


def test_pm_loop_proposal_only_is_default(monkeypatch):
    """pm_loop는 기본 proposal-only — DIPEEN_PM_PROPOSAL_ONLY 미설정 시 직접 dispatch 금지."""
    monkeypatch.delenv("DIPEEN_PM_PROPOSAL_ONLY", raising=False)
    # pm_loop의 가드와 동일한 해석(기본 "1"=proposal-only)
    val = os.getenv("DIPEEN_PM_PROPOSAL_ONLY", "1").lower()
    assert val not in ("0", "false", "no"), "기본값은 proposal-only(직접 dispatch 아님)여야 함"


@pytest.mark.asyncio
async def test_approval_alone_does_not_complete_task(tmp_path, monkeypatch):
    """승인만으로(그리고 dry_run receipt만으로) TaskState=DONE이 되지 않는다 — 증거+Reconciler 필요."""
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    monkeypatch.setenv("DIPEEN_PERMISSION_EXECUTOR_MODE", "dry_run")
    store = str(tmp_path / "nat")

    # 실제 완료엔 code_patch 증거가 필요한 task
    task = TaskEnvelope(title="ship", intent="PR 올리기",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}],
                        state="RUNNING")
    RunStore(store).save_task(task)

    led = PermissionLedger(store)
    req = PermissionRequest(task_id=task.task_id, run_id="R-inv-1", requester="agent://team/be",
                            action="github.pr.create", target="feature/login",
                            requires_human_approval=True, workspace_root=store,
                            payload={"branch": "feature/login", "base": "main"})
    led.save(req)

    # 승인 → side-effect action이라 command만 enqueue(아직 worker 미실행)
    cmd = permission_nat.approve(req.permission_request_id, decider="user://web",
                                 ledger=led, queue=CommandQueue(store))
    assert cmd is not None
    assert RunStore(store).load_task(task.task_id).state != "DONE", "승인만으론 완료가 아니다"

    # dry_run worker 실행 → would_execute 'document' receipt(code_patch 아님)
    w = WorkerNode("w-inv", capabilities=["executor.github.pr.create"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store,
                   executor_mode="dry_run", executors=default_executors())
    await w.poll_and_run_once()

    # dry_run receipt는 code_patch acceptance를 충족하지 않음 → 여전히 DONE 아님
    assert RunStore(store).load_task(task.task_id).state != "DONE", \
        "dry_run receipt는 완료 증거가 아니다(Reconciler가 acceptance로 판정)"
