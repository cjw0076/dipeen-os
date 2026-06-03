"""dipeen-agent join — 새 디바이스 원터치 합류의 capability 컨벤션을 잠근다.

join --role FE → worker가 role.fe capability로 등록 → HQ의 Assignment Routing(role.fe 태그된 command)을
이 머신만 lease. role 토큰이 라우팅의 핵심이므로 회귀하면 안 됨.
"""
from dipeen_agent.main import _join_caps, _worker_workspaces


def test_role_becomes_namespaced_routing_token():
    assert _join_caps("FE") == "provider.claude,role.fe,workspace.write"
    assert _join_caps("BE") == "provider.claude,role.be,workspace.write"


def test_role_is_lowercased():
    assert "role.qa" in _join_caps("QA").split(",")


def test_no_role_is_plain_pool_capabilities():
    assert _join_caps(None) == "provider.claude,workspace.write"


def test_worker_workspaces_builds_ref_with_repo_capability():
    ws = _worker_workspaces("workspace://ezmap-web", "ezmap-web", "/home/minjun/ezmap-web")
    assert ws[0]["workspace_ref"] == "workspace://ezmap-web"
    assert ws[0]["repo"] == "repo.ezmap-web"                 # 네임스페이스
    assert ws[0]["local_path"] == "/home/minjun/ezmap-web"   # worker-local
    assert "repo.ezmap-web" in ws[0]["capabilities"] and "workspace.write" in ws[0]["capabilities"]


def test_worker_workspaces_empty_without_ref():
    assert _worker_workspaces(None, "ezmap-web", "/path") == []   # ref 없으면 등록 안 함
