import pytest
from app.nat.core.capabilities_dipeen import register_dipeen_capabilities
from app.nat.core.capability_catalog import get, clear


@pytest.fixture(autouse=True)
def _clean():
    clear(); register_dipeen_capabilities(); yield; clear()


@pytest.mark.asyncio
async def test_team_invite_capability_mints_and_words_it(monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    async def _fake(team_id): return {"code": "ZZ99", "expires_at": "T+24h"}
    monkeypatch.setattr(cap, "mint_invite", _fake)
    res = await get("team.invite").handler({"team_id": "t", "api_url": "http://localhost:8000"}, {})
    assert res.ok and "ZZ99" in res.message
    assert any("dipeen-agent join ZZ99" in a for a in res.next_actions)
    assert res.data["invite_code"] == "ZZ99"


@pytest.mark.asyncio
async def test_workspace_open_capability_is_action_centric(monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    async def _fake(team_id): return {"code": "OPN1", "expires_at": "T+24h"}
    monkeypatch.setattr(cap, "mint_invite", _fake)
    res = await get("workspace.open").handler({"team_id": "t", "api_url": "http://localhost:8000"}, {})
    assert res.ok and res.message == "Dipeen workspace is open."
    assert any("expose" in a for a in res.next_actions)


@pytest.mark.asyncio
async def test_workspace_status_capability_summarizes(monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    monkeypatch.setattr(cap.control_plane, "list_workers", lambda: [])
    async def _lc(): return []
    monkeypatch.setattr(cap.control_plane, "list_commands", _lc)
    monkeypatch.setattr(cap.control_plane, "list_permissions", lambda status=None: [])
    res = await get("workspace.status").handler({"team_id": "t"}, {})
    assert res.ok and "0 worker" in res.message


@pytest.mark.asyncio
async def test_session_expose_capability_creates_pending(monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    from app.services.session_expose import ExposeResult
    async def _fake(*, owner_auto_approve, allow_insecure):
        return ExposeResult(ok=True, permission_id="perm_9", tunnel_started=False,
                            message="Expose requested — approve: /dipeen approve perm_9")
    monkeypatch.setattr(cap, "do_expose", _fake)
    res = await get("session.expose").handler({"team_id": "t"}, {})
    assert res.ok and "perm_9" in res.message and res.data.get("permission_id") == "perm_9"
    assert any("approve" in a for a in res.next_actions)


@pytest.mark.asyncio
async def test_session_close_capability_is_informational():
    res = await get("session.close").handler({"team_id": "t"}, {})
    assert res.ok and ("close" in res.message.lower() or "tunnel" in res.message.lower())
