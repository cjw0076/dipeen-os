"""M-routing 1단계 — Assignment Routing: 회의에서 정해진 배정이 *올바른 팀원 worker*로만 간다.

회의 "민준이 FE 맡자" → 승인 → 민준 Mac worker만 command lease → 민준 CLI에 input.
capability 누적 = AND 필터: assignment 필드가 많을수록 라우팅이 좁아진다(role pool → 특정 worker).
배정 없으면 기존 동작(provider+workspace.write) — 하위호환.
"""
import pytest

from app.nat.contracts import AssignmentSpec
from app.nat.core.command_queue import CommandQueue
from app.nat.core.proposals import confirm_proposal, propose_command
from app.nat.core.routing import assignment_to_capabilities


def test_assignment_maps_set_fields_to_capabilities():
    caps = assignment_to_capabilities(
        AssignmentSpec(role="frontend", user="minjun", repo="ezmap-web",
                       preferred_worker="worker.minjun-mac"), provider="claude")
    for c in ("provider.claude", "workspace.write", "role.frontend", "user.minjun",
              "repo.ezmap-web", "worker.minjun-mac"):
        assert c in caps, f"{c} missing from {caps}"


def test_namespacing_idempotent_and_deduped():
    caps = assignment_to_capabilities(
        AssignmentSpec(role="role.frontend", preferred_worker="minjun-mac"), provider="claude")
    assert caps.count("role.frontend") == 1          # 이미 네임스페이스면 중복 안 붙임
    assert "worker.minjun-mac" in caps               # bare id → worker.* 로 네임스페이스


def test_provider_override():
    caps = assignment_to_capabilities(AssignmentSpec(role="backend", provider="codex"), provider="claude")
    assert "provider.codex" in caps and "provider.claude" not in caps


def test_no_assignment_is_default_caps():
    assert assignment_to_capabilities(None, provider="claude") == ["provider.claude", "workspace.write"]


@pytest.mark.asyncio
async def test_fe_task_leases_only_to_frontend_worker(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="goal-1", intent="Implement login UI", provider="claude",
                        workspace_root="", proposed_by="pm", store_root=store,
                        assignment=AssignmentSpec(role="frontend", repo="ezmap-web"))
    cmd = confirm_proposal(p.proposal_id, decided_by="user://web", queue=CommandQueue(store), store_root=store)
    assert "role.frontend" in cmd.required_capabilities and "repo.ezmap-web" in cmd.required_capabilities

    q = CommandQueue(store)
    # backend worker(역할 불일치) → 못 가져감
    assert q.poll("w-backend", ["provider.claude", "role.backend", "repo.ezmap-web", "workspace.write"]) is None
    # frontend worker → lease
    leased = q.poll("w-minjun", ["provider.claude", "role.frontend", "repo.ezmap-web", "workspace.write"])
    assert leased is not None and leased.command_id == cmd.command_id


@pytest.mark.asyncio
async def test_user_specific_task_leases_only_to_that_user(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="Hotfix auth", provider="claude", workspace_root="",
                        proposed_by="pm", store_root=store,
                        assignment=AssignmentSpec(user="minjun", repo="ezmap-web"))
    cmd = confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    q = CommandQueue(store)
    # 같은 역할 풀의 다른 사람 → 못 가져감(user 불일치)
    assert q.poll("w-soojin", ["provider.claude", "user.soojin", "repo.ezmap-web", "workspace.write"]) is None
    leased = q.poll("w-minjun", ["provider.claude", "user.minjun", "repo.ezmap-web", "workspace.write"])
    assert leased is not None and leased.command_id == cmd.command_id


@pytest.mark.asyncio
async def test_no_assignment_keeps_backward_compatible_routing(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="anything", provider="claude", workspace_root="",
                        proposed_by="pm", store_root=store)            # assignment 없음
    cmd = confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    assert set(cmd.required_capabilities) == {"provider.claude", "workspace.write"}
    # provider만 맞으면 아무 worker나 가져감(기존 동작)
    assert CommandQueue(store).poll("w-any", ["provider.claude", "workspace.write"]) is not None
