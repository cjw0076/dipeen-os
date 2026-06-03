import pytest
from fastapi import HTTPException

from app.nat.core.command_queue import CommandQueue
from app.nat.contracts import Command
from app.routers import auth as auth_mod


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
