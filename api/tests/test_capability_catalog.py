import pytest
from app.nat.core.capability_catalog import (
    Capability, CapabilityResult, register, get, catalog, clear,
)


@pytest.fixture(autouse=True)
def _clean():
    clear(); yield; clear()


async def _h(ctx, params):
    return CapabilityResult(ok=True, message="hi", next_actions=["/dipeen status"])


def test_register_and_get():
    cap = Capability(name="workspace.open", human_label="Open workspace", handler=_h)
    register(cap)
    assert get("workspace.open") is cap
    assert get("nope") is None


def test_catalog_lists_registered_with_metadata():
    register(Capability(name="team.invite", human_label="Invite teammate", handler=_h,
                        surfaces=("cli", "slash", "web", "mcp")))
    cat = catalog()
    assert any(c.name == "team.invite" and "web" in c.surfaces for c in cat)


def test_capability_result_is_human_and_structured():
    r = CapabilityResult(ok=True, message="Workspace open.", next_actions=["/dipeen invite"],
                         data={"team": "X"})
    assert r.ok and r.message and r.next_actions and r.data["team"] == "X"
