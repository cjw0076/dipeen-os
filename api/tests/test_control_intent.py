"""ux-command-layer-v0 — POST /api/control/intent: slash + NL → action → human reply."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_ask_creates_proposal(client):
    r = await client.post("/api/control/intent", json={"text": "/dipeen ask fix the README Quick Start"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["verb"] == "ask" and d["data"]["proposal_id"]
    assert "Approve to dispatch" in d["message"]


async def test_natural_language_prompt_box_is_ask(client):
    # the web prompt box sends bare prose → treated as an ask for the team
    d = (await client.post("/api/control/intent", json={"text": "please fix the login bug"})).json()
    assert d["ok"] and d["verb"] == "ask" and d["data"]["proposal_id"]


async def test_assign_cap_sets_provider_on_proposal(client):
    d = (await client.post("/api/control/intent",
                           json={"text": "/dipeen assign cap:codex make a README patch"})).json()
    assert d["ok"] and d["verb"] == "assign"
    pid = d["data"]["proposal_id"]
    props = (await client.get("/api/proposals", params={"state": "proposed"})).json()
    assert next(p for p in props if p["proposal_id"] == pid)["provider"] == "codex"


async def test_approve_dispatches_proposal(client):
    pid = (await client.post("/api/control/intent",
                             json={"text": "/dipeen ask build login"})).json()["data"]["proposal_id"]
    d = (await client.post("/api/control/intent", json={"text": f"/dipeen approve {pid}"})).json()
    assert d["ok"] and d["verb"] == "approve" and "Dispatched" in d["message"]
    assert d["data"]["command_id"]


async def test_status_is_human_summary(client):
    d = (await client.post("/api/control/intent", json={"text": "/dipeen status"})).json()
    assert d["ok"] and "online" in d["message"] and "running" in d["message"]


async def test_unknown_command_returns_user_language(client):
    d = (await client.post("/api/control/intent", json={"text": "/dipeen frobnicate stuff"})).json()
    assert d["ok"] is False and "Unknown command" in d["message"]


async def test_assign_without_target_is_user_language_error(client):
    d = (await client.post("/api/control/intent", json={"text": "/dipeen assign"})).json()
    assert d["ok"] is False and "target" in d["message"]


@pytest.mark.asyncio
async def test_intent_invite_mints_real_code(client, monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    async def _fake(team_id): return {"code": "NEW1", "expires_at": "T+24h"}
    monkeypatch.setattr(cap, "mint_invite", _fake)
    r = await client.post("/api/control/intent", json={"text": "/dipeen invite"})
    body = r.json()
    assert body["ok"] and "NEW1" in body["message"]


@pytest.mark.asyncio
async def test_intent_open_is_real_not_hint(client, monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    async def _fake(team_id): return {"code": "OPN1", "expires_at": "T+24h"}
    monkeypatch.setattr(cap, "mint_invite", _fake)
    r = await client.post("/api/control/intent", json={"text": "/dipeen open"})
    body = r.json()
    assert body["ok"] and body["message"] == "Dipeen workspace is open."
    assert any("expose" in a for a in body["data"]["next_actions"])


@pytest.mark.asyncio
async def test_intent_expose_creates_pending(client, monkeypatch):
    import app.nat.core.capabilities_dipeen as cap
    from app.services.session_expose import ExposeResult
    async def _fake(*, owner_auto_approve, allow_insecure):
        return ExposeResult(ok=True, permission_id="perm_X", tunnel_started=False,
                            message="Expose requested — approve: /dipeen approve perm_X")
    monkeypatch.setattr(cap, "do_expose", _fake)
    r = await client.post("/api/control/intent", json={"text": "/dipeen expose this session"})
    body = r.json()
    assert body["ok"] and "perm_X" in body["message"]
