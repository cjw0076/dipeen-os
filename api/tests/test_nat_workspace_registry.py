"""Workspace Registry (3단계) — HQ는 팀원의 로컬 경로를 몰라야 한다.

Command는 절대경로가 아니라 `workspace://ezmap-web`(workspace_ref)을 싣고, 각 worker가 자기
local_path로 resolve한다. HQ는 workspace_ref/repo만 안다(민준의 ~/projects를 모름).
legacy workspace_root는 fallback으로 유지.
"""
import pytest

from app.nat.contracts import AssignmentSpec, Command, WorkerInfo, WorkerWorkspace
from app.nat.core.command_queue import CommandQueue
from app.nat.core.proposals import confirm_proposal, propose_command
from app.nat.core.routing import preview_routing, resolve_workspace
from app.nat.core.worker_registry import WorkerRegistry


def _ws(ref="workspace://ezmap-web", repo="repo.ezmap-web", local="/Users/minjun/projects/ezmap-web"):
    return WorkerWorkspace(workspace_ref=ref, repo=repo, local_path=local,
                           capabilities=[repo, "workspace.write", "test.npm"])


def _cmd(**kw):
    base = dict(command_type="run.start", task_id="T", run_id="R", provider="claude", required_capabilities=[])
    base.update(kw)
    return Command(**base)


def test_worker_registers_workspaces(tmp_path):
    reg = WorkerRegistry(str(tmp_path))
    reg.register(WorkerInfo(worker_id="worker.minjun-mac",
                            capabilities=["provider.claude", "role.frontend", "repo.ezmap-web", "workspace.write"],
                            workspaces=[_ws()]))
    got = reg.all()[0]
    assert got.workspaces and got.workspaces[0].workspace_ref == "workspace://ezmap-web"
    assert got.workspaces[0].local_path == "/Users/minjun/projects/ezmap-web"


def test_command_uses_workspace_ref_not_local_path(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="login UI", provider="claude", workspace_root="",
                        proposed_by="pm", store_root=store,
                        assignment=AssignmentSpec(role="frontend", repo="ezmap-web",
                                                  workspace_ref="workspace://ezmap-web"))
    cmd = confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    assert cmd.workspace_ref == "workspace://ezmap-web"
    assert cmd.repo == "repo.ezmap-web"
    assert not cmd.workspace_root           # HQ는 절대 로컬 경로를 안 싣는다


def test_worker_resolves_workspace_ref_to_local_path():
    local = resolve_workspace(_cmd(workspace_ref="workspace://ezmap-web"),
                              [_ws(local="/home/minjun/ezmap-web")])
    assert local == "/home/minjun/ezmap-web"


def test_legacy_workspace_root_still_supported_as_fallback():
    # workspace_ref 없음 → 기존 workspace_root 그대로(하위호환)
    assert resolve_workspace(_cmd(workspace_root="/legacy/abs/path"), []) == "/legacy/abs/path"
    # workspace_ref 있으나 worker에 해당 workspace 없음 → workspace_root fallback
    assert resolve_workspace(_cmd(workspace_ref="workspace://unknown", workspace_root="/fb"), [_ws()]) == "/fb"


def test_worker_without_repo_workspace_cannot_lease(tmp_path):
    store = str(tmp_path / "nat")
    p = propose_command(room_id="g", intent="x", provider="claude", workspace_root="", proposed_by="pm",
                        store_root=store, assignment=AssignmentSpec(repo="ezmap-web",
                                                                    workspace_ref="workspace://ezmap-web"))
    cmd = confirm_proposal(p.proposal_id, decided_by="u", queue=CommandQueue(store), store_root=store)
    q = CommandQueue(store)
    assert q.poll("w-noworkspace", ["provider.claude", "workspace.write"]) is None       # repo.ezmap-web 없음
    assert q.poll("w-minjun", ["provider.claude", "repo.ezmap-web", "workspace.write"]).command_id == cmd.command_id


def test_routing_preview_shows_workspace_available():
    workers = [WorkerInfo(worker_id="worker.minjun-mac",
                          capabilities=["provider.claude", "role.frontend", "repo.ezmap-web", "workspace.write"],
                          workspaces=[_ws()], state="online")]
    out = preview_routing(AssignmentSpec(role="frontend", repo="ezmap-web",
                                         workspace_ref="workspace://ezmap-web"),
                          provider="claude", workers=workers)
    assert out["matching_workers"][0]["workspace_available"] is True


@pytest.mark.asyncio
async def test_workspace_ref_survives_http_worker_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    from app.nat.worker_http import WorkerHttpClient
    w = WorkerHttpClient("worker.minjun-mac", ["provider.claude", "repo.ezmap-web", "workspace.write"],
                         http=client, workspaces=[_ws()])
    await w.register()
    workers = (await client.get("/api/workers")).json()
    me = next(x for x in workers if x["worker_id"] == "worker.minjun-mac")
    assert me["workspaces"][0]["workspace_ref"] == "workspace://ezmap-web"
    assert me["workspaces"][0]["local_path"] == "/Users/minjun/projects/ezmap-web"
