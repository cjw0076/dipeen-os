"""ux-command-layer-v0 — GET /api/control/capabilities: the ⌘K palette source.

Enumerates the executable commands a web ⌘K palette renders. Combines the core verbs
(handled directly in /intent) with the capability catalog (open/invite/expose/close).
Each command is a ready-to-run slash template; needs_input marks the ones the user must
finish typing before the palette submits to /api/control/intent.
"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_lists_core_verbs_and_catalog_caps(client):
    d = (await client.get("/api/control/capabilities")).json()
    cmds = d["commands"]
    ids = {c["id"] for c in cmds}
    # core verbs handled directly in /intent
    assert {"status", "workers", "permissions", "ask", "assign"} <= ids
    # capabilities from the catalog
    assert {"workspace.open", "team.invite", "session.expose", "session.close"} <= ids


async def test_each_command_is_a_runnable_slash_template(client):
    cmds = (await client.get("/api/control/capabilities")).json()["commands"]
    for c in cmds:
        assert c["id"] and c["label"]
        assert c["template"].startswith("/dipeen ")
        assert isinstance(c["needs_input"], bool)


async def test_freeform_verbs_need_input_noarg_verbs_do_not(client):
    by_id = {c["id"]: c for c in (await client.get("/api/control/capabilities")).json()["commands"]}
    assert by_id["ask"]["needs_input"] is True
    assert by_id["assign"]["needs_input"] is True
    assert by_id["status"]["needs_input"] is False
    assert by_id["workspace.open"]["needs_input"] is False


async def test_self_heals_when_catalog_cleared(client):
    from app.nat.core import capability_catalog
    capability_catalog.clear()  # simulate test-isolation wiping the global registry
    d = (await client.get("/api/control/capabilities")).json()
    ids = {c["id"] for c in d["commands"]}
    assert "workspace.open" in ids  # re-registered on demand
