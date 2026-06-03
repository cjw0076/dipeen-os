"""NAT M5 — in-process 파이프라인: outbound→adapter.run→inbound→verify→reconcile→persist.

fake runner로 전체 배선을 hermetic하게 증명(실측 claude/codex는 cli로 별도 실행). worker_execute /
core_reconcile 솔기 = 미래 Core↔Worker 분리점(M6).
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.nat.adapters.base import ExecResult
from app.nat.core import pipeline
from app.nat.core.run_store import RunStore
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.eventlog import EventLog
from app.nat import providers as _providers


@pytest.fixture(autouse=True)
def _providers_ready():
    _providers.register_defaults()
    yield


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-pipe-"))
    for args in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                 ["git", "config", "user.name", "t"]):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def _store() -> Path:
    return Path(tempfile.mkdtemp(prefix="nat-store-"))


class _FakeRunner:
    """argv 캡처 + 정해진 ExecResult. writes 주면 워크스페이스에 파일 생성(agent 편집 시뮬)."""

    def __init__(self, result: ExecResult, *, writes: str | None = None):
        self.result = result
        self.writes = writes
        self.calls: list[list[str]] = []

    async def __call__(self, argv, *, cwd, env, timeout_sec):
        self.calls.append(list(argv))
        if self.writes:
            (Path(cwd) / self.writes).write_text("edited\n", encoding="utf-8")
        return self.result


@pytest.mark.asyncio
async def test_run_task_done_when_agent_edits_file():
    ws, store = _git_repo(), _store()
    fake = _FakeRunner(ExecResult(0, "implemented", ""), writes="page.tsx")
    outcome = await pipeline.run_task(
        "로그인 UI 구현", provider="claude", workspace_root=str(ws), store_root=str(store),
        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}], runner=fake)
    assert outcome.state == "DONE"
    assert any(a.type == "code_patch" for a in outcome.normalized.artifacts)
    # 영속 확인
    assert RunStore(store).load_task(outcome.task.task_id).state == "DONE"
    assert ArtifactStore(store).list(task_id=outcome.task.task_id)


@pytest.mark.asyncio
async def test_run_task_false_done_to_needs_retry():
    ws, store = _git_repo(), _store()
    fake = _FakeRunner(ExecResult(0, "i did nothing", ""))         # 변경 없음 → 거짓 done
    outcome = await pipeline.run_task(
        "do nothing", provider="codex", workspace_root=str(ws), store_root=str(store), runner=fake)
    assert outcome.state == "NEEDS_RETRY"
    assert RunStore(store).load_task(outcome.task.task_id).state == "NEEDS_RETRY"


@pytest.mark.asyncio
async def test_run_task_persists_events_and_state_reconciled():
    ws, store = _git_repo(), _store()
    fake = _FakeRunner(ExecResult(0, "ok", ""), writes="x.ts")
    outcome = await pipeline.run_task("edit", provider="claude",
                                      workspace_root=str(ws), store_root=str(store), runner=fake)
    kinds = {e.event_type for e in EventLog(store).by_task(outcome.task.task_id)}
    assert "artifact.produced" in kinds and "state.reconciled" in kinds


@pytest.mark.asyncio
async def test_inspect_task_returns_structured_view():
    ws, store = _git_repo(), _store()
    fake = _FakeRunner(ExecResult(0, "done", ""), writes="login.tsx")
    outcome = await pipeline.run_task("build", provider="claude",
                                      workspace_root=str(ws), store_root=str(store), runner=fake)
    view = pipeline.inspect_task(outcome.task.task_id, store_root=str(store))
    assert view["state"] == "DONE"
    assert len(view["runs"]) == 1 and view["runs"][0]["identity"] == "agent://team/claude"
    types = {a["type"] for a in view["artifacts"]}
    assert "code_patch" in types and "file_change_set" in types


@pytest.mark.asyncio
async def test_worker_core_seam_independently_callable():
    """worker_execute(Worker측) → core_reconcile(Core측) 분리 호출 — M6 분리점 검증."""
    from app.nat.contracts import AgentIdentity, AgentBinding, TaskEnvelope, Run
    ws, store = _git_repo(), _store()
    task = TaskEnvelope(title="t", intent="i")
    identity = AgentIdentity(identity_id="agent://team/claude", role="claude",
                             binding=AgentBinding(adapter="claude"))
    run = Run(task_id=task.task_id, identity_id=identity.identity_id)
    RunStore(store).save_task(task)
    fake = _FakeRunner(ExecResult(0, "ok", ""), writes="a.ts")
    _, _, normalized = await pipeline.worker_execute(
        task, identity, run_id=run.run_id, workspace_root=str(ws), runner=fake)
    result = pipeline.core_reconcile(task, run, normalized, store_root=str(store))
    assert result.state == "DONE"                                  # Worker 산출 → Core 결정
