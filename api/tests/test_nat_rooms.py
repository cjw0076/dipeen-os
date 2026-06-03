"""NAT M8 — Room/Message + CommandProposal (agentic Slack skeleton, 제품 트랙).

안전 불변식(D-001/§17): **message ≠ 실행.** message.created → command.proposed → (confirm) → command.queued.
채팅과 실행이 섞이지 않는다 — 제안만으론 아무것도 실행되지 않고, 사람/정책 confirm 후에만 enqueue.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.nat.contracts import Room, Message, SenderRef
from app.nat.adapters.base import ExecResult
from app.nat.core import proposals
from app.nat.core.rooms import RoomStore, MessageLog
from app.nat.core.proposals import ProposalStore
from app.nat.core.command_queue import CommandQueue
from app.nat.core.eventlog import EventLog
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.worker import WorkerNode
from app.nat import providers as _providers


def _store() -> str:
    return tempfile.mkdtemp(prefix="nat-room-")


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-room-ws-"))
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


# ════════ 안전 불변식: message ≠ 실행 ════════
def test_post_message_does_not_enqueue_command():
    store = _store()
    RoomStore(store).create(Room(room_id="task-T-1", room_type="task", ref_id="T-1"))
    MessageLog(store).post(Message(room_id="task-T-1", sender=SenderRef(type="human", id="user://cjw"),
                                   body="로그인 UI를 OMO로 구현해줘"))
    assert CommandQueue(store)._all() == []                      # 메시지는 실행이 아님
    assert len(MessageLog(store).read("task-T-1")) == 1          # 방에 기록됨
    assert "discussion.message" in {e.event_type for e in EventLog(store).read_all()}  # event log에도


def test_proposal_alone_does_not_enqueue():
    store, ws = _store(), _git_repo()
    p = proposals.propose_command(room_id="r1", intent="로그인 구현", provider="claude",
                                  workspace_root=str(ws), proposed_by="agent://team/pm", store_root=store)
    assert p.state == "proposed"
    assert CommandQueue(store)._all() == []                      # 제안만으론 실행 안 됨
    assert ProposalStore(store).get(p.proposal_id).state == "proposed"


def test_confirm_proposal_enqueues_command():
    store, ws = _store(), _git_repo()
    p = proposals.propose_command(room_id="r1", intent="로그인 구현", provider="claude",
                                  workspace_root=str(ws), proposed_by="agent://team/pm", store_root=store)
    cmd = proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw",
                                     queue=CommandQueue(store), store_root=store)
    assert cmd is not None and cmd.command_type == "run.start"
    assert len(CommandQueue(store)._all()) == 1                  # 확인 후에만 enqueue
    saved = ProposalStore(store).get(p.proposal_id)
    assert saved.state == "confirmed" and saved.command_id == cmd.command_id
    assert "decision.accepted" in {e.event_type for e in EventLog(store).read_all()}


def test_reject_proposal_no_command():
    store = _store()
    p = proposals.propose_command(room_id="r1", intent="x", provider="codex", workspace_root="/ws",
                                  proposed_by="agent://team/pm", store_root=store)
    proposals.reject_proposal(p.proposal_id, decided_by="user://cjw", store_root=store)
    assert ProposalStore(store).get(p.proposal_id).state == "rejected"
    assert CommandQueue(store)._all() == []
    # confirm a rejected proposal → no-op
    assert proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw",
                                      queue=CommandQueue(store), store_root=store) is None


# ════════ 통합: confirm → worker pull → 실행 → DONE ════════
@pytest.mark.asyncio
async def test_confirmed_proposal_flows_through_worker_to_done():
    store, ws = _store(), _git_repo()
    _providers.register_defaults()
    p = proposals.propose_command(room_id="r1", intent="구현", provider="claude", workspace_root=str(ws),
                                  proposed_by="agent://team/pm", store_root=store,
                                  acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}])
    proposals.confirm_proposal(p.proposal_id, decided_by="user://cjw",
                               queue=CommandQueue(store), store_root=store)
    w = WorkerNode("w1", capabilities=["provider.claude", "workspace.write"], queue=CommandQueue(store),
                   registry=WorkerRegistry(store), store_root=store)
    w.register()
    result = await w.poll_and_run_once(runner=_FakeRunner(ExecResult(0, "done", ""), writes="page.tsx"))
    assert result.state == "DONE"                               # message→propose→confirm→queue→worker→DONE


# ════════ typed room ════════
def test_room_store_typed_rooms_attached_to_objects():
    store = _store()
    rs = RoomStore(store)
    rs.create(Room(room_id="goal-G-1", room_type="goal", ref_id="G-1", title="EZmap launch"))
    rs.create(Room(room_id="perm-P-1", room_type="permission", ref_id="P-1"))
    assert rs.get("goal-G-1").room_type == "goal" and rs.get("goal-G-1").ref_id == "G-1"
    assert {r.room_type for r in rs.list()} == {"goal", "permission"}


def test_core_rooms_proposals_do_not_import_adapters():
    import app.nat.core.rooms as rm
    import app.nat.core.proposals as pr
    forbidden = ("ClaudeAdapter", "CodexAdapter", "ClaudeNATPlugin", "WorkerNode", "default_runner")
    for m in (rm, pr):
        for f in forbidden:
            assert not hasattr(m, f), f"Isolation 위반: {m.__name__} exposes {f}"
