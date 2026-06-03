"""NAT M10a — WorkerHttpClient E2E: 원격 worker가 control_plane HTTP 엔드포인트로 붙어 한 사이클.

사용자님 control_plane 라우터(서버)를 *그대로 사용*해 검증한다(서버 코드 미수정). conftest의 ASGI
client를 worker의 HTTP transport로 주입 → register → poll → 로컬 실행(fake) → result POST → Core reconcile.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.nat.adapters.base import ExecResult
from app.nat.contracts import TaskEnvelope
from app.nat.core import conductor
from app.nat.core.command_queue import CommandQueue
from app.nat.core.run_store import RunStore
from app.nat.worker_http import WorkerHttpClient
from app.nat import providers as _providers


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-http-ws-"))
    for a in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(a, cwd=root, check=True, capture_output=True)
    return root


class _FakeRunner:
    def __init__(self, result, *, writes=None):
        self.result, self.writes, self.calls = result, writes, []

    async def __call__(self, argv, *, cwd, env, timeout_sec):
        self.calls.append(list(argv))
        if self.writes:
            (Path(cwd) / self.writes).write_text("x\n", encoding="utf-8")
        return self.result


@pytest.mark.asyncio
async def test_http_worker_register_poll_execute_reconcile(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))      # control_plane store 격리
    store = str(tmp_path / "nat")
    _providers.register_defaults()
    ws = _git_repo()

    # Core: task를 command queue에 dispatch(서버가 읽는 같은 store)
    task = TaskEnvelope(title="login", intent="로그인 구현",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}])
    conductor.dispatch_run(CommandQueue(store), task, provider="claude",
                           workspace_root=str(ws), store_root=store)

    # 원격 worker: conftest ASGI client를 HTTP transport로 주입, fake runner로 hermetic
    w = WorkerHttpClient("w-remote", ["provider.claude", "workspace.write"], http=client,
                         runner=_FakeRunner(ExecResult(0, "implemented", ""), writes="page.tsx"))
    reg = await w.register()
    assert reg["worker_id"] == "w-remote"

    ran = await w.poll_once()                                      # poll→ack→로컬실행→result POST
    assert ran is True
    assert await w.poll_once() is False                            # 빈 큐 → 처리 없음

    # Core가 증거로 reconcile → DONE (store 직접 + HTTP 둘 다 확인)
    assert RunStore(store).load_task(task.task_id).state == "DONE"
    arts = (await client.get("/api/artifacts", params={"task_id": task.task_id})).json()
    assert any(a["type"] == "code_patch" for a in arts)            # HTTP로 round-trip 영속 확인


@pytest.mark.asyncio
async def test_http_worker_capability_mismatch_polls_nothing(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    store = str(tmp_path / "nat")
    _providers.register_defaults()
    ws = _git_repo()
    conductor.dispatch_run(CommandQueue(store), TaskEnvelope(title="t", intent="i"),
                           provider="codex", workspace_root=str(ws), store_root=store)
    # claude만 가진 worker는 codex command를 못 가져감
    w = WorkerHttpClient("w-claude", ["provider.claude", "workspace.write"], http=client,
                         runner=_FakeRunner(ExecResult(0, "", "")))
    await w.register()
    assert await w.poll_once() is False
