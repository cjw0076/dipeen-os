"""provider.fake — 키 없는 결정론적 provider (BYOK 데모 마찰의 답, Gate5 키스톤).

CLI/네트워크/키 0. 워크스페이스에 결정론적 파일 1개 작성 → **진짜** git diff → code_patch → reconcile DONE.
공개 데모 참가자가 키 없이 전 루프(실행→증거→검증)를 본다. dry_run permission과 함께 키스톤.
"""
import subprocess
from pathlib import Path

import pytest

from app.nat import providers as _providers
from app.nat.contracts import TaskEnvelope
from app.nat.core import conductor
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.command_queue import CommandQueue
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.worker import WorkerNode


def _git_repo(root: Path) -> Path:
    ws = root / "ws"
    ws.mkdir()
    for a in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(a, cwd=ws, check=True, capture_output=True)
    return ws


def test_fake_plugin_is_registered():
    _providers.register_defaults()
    from app.nat.core.registry import get_plugin
    assert get_plugin("fake").name == "fake"      # 키 없이 쓸 수 있는 provider가 registry에 있음


@pytest.mark.asyncio
async def test_fake_provider_executes_keyless_to_done(tmp_path):
    _providers.register_defaults()
    ws = _git_repo(tmp_path)
    store = str(tmp_path / "nat")

    task = TaskEnvelope(title="login", intent="로그인 기능 구현",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}])
    conductor.dispatch_run(CommandQueue(store), task, provider="fake",
                           workspace_root=str(ws), store_root=store)

    worker = WorkerNode("w-demo", capabilities=["provider.fake", "workspace.write"],
                        queue=CommandQueue(store), registry=WorkerRegistry(store), store_root=store)
    worker.register()
    result = await worker.poll_and_run_once()     # runner 불요 — fake는 CLI를 안 켠다

    # 진짜 실행 결과: 파일이 실제로 생겼고, code_patch artifact + DONE
    assert any(ws.glob("*")), "fake provider는 진짜 파일을 만든다"
    assert result is not None and result.state == "DONE"
    arts = ArtifactStore(store).list(task_id=task.task_id)
    assert any(a.type == "code_patch" for a in arts), "키 없이도 code_patch 증거 생성"


@pytest.mark.asyncio
async def test_fake_provider_no_key_no_network(tmp_path, monkeypatch):
    # ANTHROPIC_API_KEY가 없어도(키 0) fake는 동작한다
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _providers.register_defaults()
    ws = _git_repo(tmp_path)
    store = str(tmp_path / "nat")
    task = TaskEnvelope(title="t", intent="i",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}])
    conductor.dispatch_run(CommandQueue(store), task, provider="fake", workspace_root=str(ws), store_root=store)
    w = WorkerNode("w", capabilities=["provider.fake", "workspace.write"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store)
    w.register()
    assert (await w.poll_and_run_once()).state == "DONE"
