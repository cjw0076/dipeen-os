import importlib

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from app.nat.core.command_queue import CommandQueue
from app.nat.contracts import Command
from app.routers import auth as auth_mod


# ── Task 1: queue lease_id ────────────────────────────────────────

def test_poll_assigns_lease_id(tmp_path):
    q = CommandQueue(tmp_path)
    q.enqueue(Command(provider="claude", required_capabilities=[]))
    leased = q.poll("wkr_a", [])
    assert leased is not None
    assert leased.lease_id is not None and len(leased.lease_id) >= 8
    assert leased.lease_owner == "wkr_a"


# ── Task 2: worker JWT ────────────────────────────────────────────

def _worker_token(team="teamA", wid="wkr_1"):
    return auth_mod._issue_worker_jwt(team, wid)


def test_worker_jwt_roundtrip(monkeypatch):
    monkeypatch.setattr(auth_mod, "_REQUIRE_AUTH", True)
    tok = _worker_token("teamA", "wkr_1")
    ident = auth_mod.get_worker_identity("wkr_1", authorization=f"Bearer {tok}")
    assert ident.team_id == "teamA"
    assert ident.worker_id == "wkr_1"


def test_worker_jwt_rejects_team_token(monkeypatch):
    monkeypatch.setattr(auth_mod, "_REQUIRE_AUTH", True)
    team_tok = auth_mod._issue_team_jwt("teamA")
    with pytest.raises(HTTPException) as e:
        auth_mod.get_worker_identity("wkr_1", authorization=f"Bearer {team_tok}")
    assert e.value.status_code == 403


def test_worker_jwt_rejects_id_mismatch(monkeypatch):
    monkeypatch.setattr(auth_mod, "_REQUIRE_AUTH", True)
    tok = _worker_token("teamA", "wkr_1")
    with pytest.raises(HTTPException) as e:
        auth_mod.get_worker_identity("wkr_OTHER", authorization=f"Bearer {tok}")
    assert e.value.status_code == 403


def test_worker_identity_fallback_when_auth_off(monkeypatch):
    monkeypatch.setattr(auth_mod, "_REQUIRE_AUTH", False)
    ident = auth_mod.get_worker_identity("wkr_x", authorization=None)
    assert ident.worker_id == "wkr_x"
    assert ident.team_id == "default-team"


def test_worker_identity_requires_token_when_strict(monkeypatch):
    monkeypatch.setattr(auth_mod, "_REQUIRE_AUTH", True)
    with pytest.raises(HTTPException) as e:
        auth_mod.get_worker_identity("wkr_x", authorization=None)
    assert e.value.status_code == 401


# ── Task 3/4: endpoint auth (TestClient) ──────────────────────────

def _client(monkeypatch, require_auth):
    monkeypatch.setenv("DIPEEN_REQUIRE_AUTH", "true" if require_auth else "false")
    import app.config as config
    importlib.reload(config)
    import app.routers.auth as a
    importlib.reload(a)
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app), a


def test_register_requires_team_jwt_when_strict(monkeypatch):
    c, _ = _client(monkeypatch, True)
    r = c.post("/api/workers", json={"worker_id": "ignored", "capabilities": []})
    assert r.status_code == 401


def test_register_issues_worker_token_and_canonical_id(monkeypatch):
    c, a = _client(monkeypatch, True)
    team_tok = a._issue_team_jwt("teamA")
    r = c.post("/api/workers", json={"worker_id": "client-hint", "capabilities": ["provider.claude"]},
               headers={"Authorization": f"Bearer {team_tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data["worker_id"].startswith("wkr_")
    assert data["worker_id"] != "client-hint"        # 서버 생성, 클라 입력 무시
    assert data["worker_token"]
    decoded = a._decode_jwt(data["worker_token"])
    assert decoded["typ"] == "worker" and decoded["team_id"] == "teamA"
