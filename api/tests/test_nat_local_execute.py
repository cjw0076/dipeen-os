"""NAT M10 gap② — local_execute 실측: 승인된 git.commit을 worker가 *실제로* 실행(dry_run 아님).

dry_run/manual_handoff는 side effect 0(would_execute 미리보기)지만, local_execute는 concrete
ExecutorPlugin으로 진짜 side effect를 일으키고 executor_success 증거를 남겨야 한다. git.commit=로컬·가역
실 side effect라 외부 호출 없이 local_execute 경로를 실증한다. **Core는 여전히 실행하지 않는다**(worker가 함).
"""
import asyncio
import subprocess
from pathlib import Path

import pytest

from app.nat.contracts import Command, TaskEnvelope
from app.nat.core.command_queue import CommandQueue
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.executors import default_executors
from app.nat.worker import WorkerNode


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _staged_repo(root: Path) -> Path:
    ws = root / "ws"
    ws.mkdir()
    _git(["init", "-q"], ws)
    _git(["config", "user.email", "t@t"], ws)
    _git(["config", "user.name", "t"], ws)
    (ws / "feature.txt").write_text("approved change\n", encoding="utf-8")
    _git(["add", "."], ws)               # staged, 아직 commit 0
    return ws


def _commit_count(ws: Path) -> int:
    r = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=ws, capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 else 0


@pytest.mark.asyncio
async def test_local_execute_git_commit_real_side_effect(tmp_path):
    store = str(tmp_path / "nat")
    ws = _staged_repo(tmp_path)
    assert _commit_count(ws) == 0                       # baseline: 실제 커밋 없음

    task = TaskEnvelope(title="commit", intent="승인된 변경 커밋")
    RunStore(store).save_task(task)
    queue = CommandQueue(store)
    cmd = queue.enqueue(Command(
        command_type="permission.execute", task_id=task.task_id, run_id="R-le-1", provider="",
        permission_id="P-le-1", required_capabilities=["executor.git.commit"],
        workspace_root=str(ws),
        payload={"action": "git.commit", "target": "main", "message": "dipeen: approved commit"}))

    # local_execute + 기본 executor(git.commit) — 진짜 실행
    w = WorkerNode("w-le", capabilities=["executor.git.commit"], queue=queue,
                   registry=WorkerRegistry(store), store_root=store,
                   executor_mode="local_execute", executors=default_executors())
    await w.poll_and_run_once()

    # ① 진짜 side effect: 실제 커밋이 생겼다
    assert _commit_count(ws) == 1, "local_execute는 진짜 git commit을 만들어야 함"
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True).stdout
    assert "approved commit" in log

    # ② receipt 증거 = executor_success(passed, would_execute 아님)
    from app.nat.core.artifact_store import ArtifactStore
    receipts = [a for a in ArtifactStore(store).list(task_id=task.task_id) if "receipt" in a.title]
    assert receipts, "receipt artifact가 있어야 함"
    kinds = {e.kind: e.passed for e in receipts[0].evidence}
    assert kinds.get("executor_success") is True, "local_execute 성공은 executor_success=True"
    assert "would_execute" not in kinds, "local_execute는 dry_run(would_execute)이 아니어야 함"

    # ③ command 완료
    assert queue.get(cmd.command_id).state == "completed"


@pytest.mark.asyncio
async def test_dry_run_does_not_commit(tmp_path):
    """대조군: 기본 dry_run이면 같은 command라도 진짜 커밋이 생기지 않는다(안전 기본값)."""
    store = str(tmp_path / "nat")
    ws = _staged_repo(tmp_path)

    task = TaskEnvelope(title="commit", intent="커밋")
    RunStore(store).save_task(task)
    queue = CommandQueue(store)
    queue.enqueue(Command(
        command_type="permission.execute", task_id=task.task_id, run_id="R-le-2", provider="",
        permission_id="P-le-2", required_capabilities=["executor.git.commit"], workspace_root=str(ws),
        payload={"action": "git.commit", "target": "main", "message": "should not happen"}))

    w = WorkerNode("w-dry", capabilities=["executor.git.commit"], queue=queue,
                   registry=WorkerRegistry(store), store_root=store,
                   executor_mode="dry_run", executors=default_executors())
    await w.poll_and_run_once()

    assert _commit_count(ws) == 0, "dry_run은 진짜 side effect 0"
