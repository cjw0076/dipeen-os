"""NAT M9 — Worker 런타임(drain/run_loop = agent-client 후신) + proposal-only 플래닝(pm_loop 강등).

성공 기준(사용자 D-M9): "기존 agent-client가 NAT Worker로 한 사이클 실행". UI 아님.
PM은 plan을 *제안*만(propose_plan), 실행 enqueue는 confirm 후에만 → worker가 pull해 한 사이클 실행.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.nat.adapters.base import ExecResult
from app.nat.core import proposals
from app.nat.core.command_queue import CommandQueue
from app.nat.core.proposals import ProposalStore
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.worker import WorkerNode
from app.nat import providers as _providers


@pytest.fixture(autouse=True)
def _providers_ready():
    _providers.register_defaults()
    yield


def _store() -> str:
    return tempfile.mkdtemp(prefix="nat-wrt-")


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-wrt-ws-"))
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


def _worker(store, caps=("provider.claude", "provider.codex", "workspace.write")):
    w = WorkerNode("w-node", capabilities=list(caps), queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store)
    w.register()
    return w


# ════════ proposal-only 플래닝 (pm_loop 강등) ════════
def test_propose_plan_creates_proposals_no_commands():
    store, ws = _store(), _git_repo()
    plan = [
        {"intent": "기존 auth 조사", "provider": "claude", "workspace_root": str(ws)},
        {"intent": "로그인 UI 구현", "provider": "codex", "workspace_root": str(ws),
         "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}]},
    ]
    props = proposals.propose_plan(plan, room_id="goal-G1", store_root=store, proposed_by="agent://team/pm")
    assert len(props) == 2 and all(p.state == "proposed" for p in props)
    assert CommandQueue(store)._all() == []                     # PM 제안만으론 실행 0


# ════════ worker drain — 한 사이클 ════════
@pytest.mark.asyncio
async def test_worker_drain_processes_confirmed_command():
    store, ws = _store(), _git_repo()
    [p] = proposals.propose_plan([{"intent": "구현", "provider": "claude", "workspace_root": str(ws),
                                   "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}]}],
                                 room_id="r1", store_root=store, proposed_by="agent://team/pm")
    proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw", queue=CommandQueue(store), store_root=store)

    results = await _worker(store).drain(runner=_FakeRunner(ExecResult(0, "done", ""), writes="page.tsx"))
    assert len(results) == 1 and results[0].state == "DONE"     # 한 사이클 실행
    assert RunStore(store).load_task(ProposalStore(store).get(p.proposal_id).task_id).state == "DONE"


@pytest.mark.asyncio
async def test_worker_drain_empty_queue_returns_nothing():
    assert await _worker(_store()).drain(runner=_FakeRunner(ExecResult(0, "", ""))) == []


@pytest.mark.asyncio
async def test_worker_drain_multiple_confirmed():
    store, ws = _store(), _git_repo()
    props = proposals.propose_plan(
        [{"intent": f"task{i}", "provider": "claude", "workspace_root": str(ws)} for i in range(3)],
        room_id="r1", store_root=store, proposed_by="agent://team/pm")
    for p in props:
        proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw",
                                   queue=CommandQueue(store), store_root=store)
    results = await _worker(store).drain(runner=_FakeRunner(ExecResult(0, "ok", ""), writes="f.ts"))
    assert len(results) == 3 and all(r.state == "DONE" for r in results)


# ════════ run_loop (유한 반복, 테스트용) ════════
@pytest.mark.asyncio
async def test_run_loop_bounded_processes_then_idles():
    store, ws = _store(), _git_repo()
    [p] = proposals.propose_plan([{"intent": "x", "provider": "claude", "workspace_root": str(ws)}],
                                 room_id="r1", store_root=store, proposed_by="agent://team/pm")
    proposals.confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    w = _worker(store)
    await w.run_loop(runner=_FakeRunner(ExecResult(0, "ok", ""), writes="f.ts"),
                     idle_sleep=0.0, max_iterations=2)         # 1회차 처리, 2회차 idle
    cmd_id = ProposalStore(store).get(p.proposal_id).command_id
    assert CommandQueue(store).get(cmd_id).state == "completed"


# ════════ 전체 사이클: plan → propose → confirm → worker → DONE ════════
@pytest.mark.asyncio
async def test_full_cycle_plan_propose_confirm_worker_done():
    store, ws = _store(), _git_repo()
    [p] = proposals.propose_plan([{"intent": "로그인 구현", "provider": "claude", "workspace_root": str(ws),
                                   "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}]}],
                                 room_id="goal-G1", store_root=store, proposed_by="agent://team/pm")
    assert CommandQueue(store)._all() == []                     # 제안 단계: 실행 0
    proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw", queue=CommandQueue(store), store_root=store)
    results = await _worker(store).drain(runner=_FakeRunner(ExecResult(0, "implemented", ""), writes="login.tsx"))
    assert results[0].state == "DONE"
