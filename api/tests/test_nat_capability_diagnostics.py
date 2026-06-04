"""T1 — capability 불일치 가시화 (sync queue): poll None일 때 '왜 안 잡혔는지' 설명.

command_queue.poll이 capability subset 불일치를 조용히 skip하던 걸, unmatched_capabilities가
missing 토큰과 함께 돌려줘서 워커가 사람 문장으로 안내할 수 있게 한다.
"""
from app.nat.contracts import AssignmentSpec
from app.nat.core.command_queue import CommandQueue
from app.nat.core.proposals import confirm_proposal, propose_command


def test_unmatched_explains_missing_capabilities(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="build login UI", provider="claude", workspace_root="",
                        proposed_by="pm", store_root=store,
                        assignment=AssignmentSpec(role="frontend", repo="ezmap-web"))
    cmd = confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    q = CommandQueue(store)
    caps = ["provider.claude", "workspace.write"]      # missing role.frontend / repo.ezmap-web
    assert q.poll("w", caps) is None                    # silent skip today
    unmatched = q.unmatched_capabilities(caps)          # NEW: explains why
    assert len(unmatched) == 1
    u = unmatched[0]
    assert u["command_id"] == cmd.command_id
    assert "role.frontend" in u["missing"] and "repo.ezmap-web" in u["missing"]
    assert "provider.claude" not in u["missing"]


def test_unmatched_empty_when_caps_match(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="x", provider="claude", workspace_root="",
                        proposed_by="pm", store_root=store)
    confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    q = CommandQueue(store)
    assert q.unmatched_capabilities(["provider.claude", "workspace.write"]) == []
