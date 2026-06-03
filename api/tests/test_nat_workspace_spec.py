"""TeamWorkspaceSpec — host CLI가 만들고 web UI는 렌더만. mode가 패널 구성을 결정.

핵심 원칙: **web UI가 스스로 판단하지 않는다.** host가 spec(.dipeen/workspace.yaml)을 만들고 web은 spec.ui.panels를 렌더.
UI 코드 수정 없이 mode만 바꿔 화면이 달라진다(public_demo/team/production/debug).
"""
import pytest
import yaml

from app.nat import cli as nat_cli
from app.nat.core.workspace_spec import (TeamWorkspaceSpec, WorkspaceRepo, default_spec, load_spec, save_spec)


def test_public_demo_mode_has_join_and_demo_and_dry_run():
    spec = default_spec("public_demo", workspace_id="ezmap-demo")
    assert spec.mode == "public_demo"
    assert "join_panel" in spec.ui.panels and "demo_panel" in spec.ui.panels
    assert spec.ui.show_dry_run_banner is True
    assert spec.policies["permission_executor_mode"] == "dry_run"


def test_team_mode_has_rooms_and_taskboard():
    spec = default_spec("team", workspace_id="ezmap")
    assert "meeting_room" in spec.ui.panels and "task_board" in spec.ui.panels
    assert "join_panel" not in spec.ui.panels        # 팀 모드는 join 패널 전면 아님


def test_debug_mode_exposes_internals():
    spec = default_spec("debug", workspace_id="d")
    for p in ("event_log", "command_queue", "provider_inspect"):
        assert p in spec.ui.panels


def test_providers_are_cli_wrappers_not_keys():
    spec = default_spec("team", workspace_id="x")
    # OMO/Hermes도 CLI 래퍼(local_cli/experimental) — API 키가 아니다
    assert spec.providers["claude"] == "local_cli"
    assert spec.providers["omo"] in ("experimental", "local_cli")
    assert "fake" in spec.providers


def test_save_load_roundtrip_yaml(tmp_path):
    spec = default_spec("public_demo", workspace_id="demo")
    path = save_spec(spec, str(tmp_path))
    assert path.name == "workspace.yaml" and path.parent.name == ".dipeen"
    loaded = load_spec(str(tmp_path))
    assert isinstance(loaded, TeamWorkspaceSpec)
    assert loaded.workspace_id == "demo" and loaded.mode == "public_demo"
    assert loaded.ui.panels == spec.ui.panels


def test_load_missing_returns_none(tmp_path):
    assert load_spec(str(tmp_path)) is None     # 없으면 None(정직한 부재)


def test_workspace_yaml_uses_project_and_team_sections(tmp_path):
    spec = default_spec("public_demo", workspace_id="ezmap-demo")
    spec.project.repos.append(WorkspaceRepo(id="repo.ezmap-web", workspace_ref="workspace://ezmap-web"))
    path = save_spec(spec, str(tmp_path))

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert raw["workspace_id"] == "ezmap-demo"
    assert raw["mode"] == "public_demo"
    assert raw["ui"]["layout"] == "control_tower"
    assert "join_panel" in raw["ui"]["panels"]
    assert raw["project"]["repos"] == [{"id": "repo.ezmap-web", "workspace_ref": "workspace://ezmap-web"}]
    assert raw["team"]["roles"] == ["frontend", "backend", "qa", "memory"]
    assert "repos" not in raw
    assert "roles" not in raw


def test_dipeen_workspace_init_cli_writes_spec(tmp_path):
    rc = nat_cli.main([
        "--store", str(tmp_path / "store"),
        "workspace", "init",
        "--mode", "public-demo",
        "--id", "ezmap-demo",
        "--root", str(tmp_path),
    ])

    assert rc == 0
    loaded = load_spec(str(tmp_path))
    assert loaded is not None
    assert loaded.workspace_id == "ezmap-demo"
    assert loaded.mode == "public_demo"
    assert "demo_panel" in loaded.ui.panels


@pytest.mark.asyncio
async def test_workspace_spec_api_reads_workspace_yaml(client, tmp_path, monkeypatch):
    root = tmp_path / "hq"
    spec = default_spec("debug", workspace_id="debug-room")
    save_spec(spec, root)
    monkeypatch.setenv("DIPEEN_WORKSPACE_ROOT", str(root))

    response = await client.get("/api/workspace/spec")

    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == "debug-room"
    assert body["mode"] == "debug"
    assert body["ui"]["panels"] == spec.ui.panels
    assert body["project"]["repos"] == []
    assert body["team"]["roles"] == ["frontend", "backend", "qa", "memory"]
