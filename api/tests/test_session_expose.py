from typing import get_args

import pytest

from app.nat.contracts import PermissionAction
from app.nat.core import policy


def test_session_expose_is_a_permission_action_requiring_approval():
    assert "session.expose" in get_args(PermissionAction)
    assert policy.classify("session.expose") == "require_human_approval"


from app.services.session_expose import request_expose, ExposeDeps, ExposeResult


def _deps(*, auth=True):
    calls = {"create": 0, "approve": 0, "receipt": 0, "tunnel": 0}
    def create(): calls["create"] += 1; return "perm_1"
    def approve(pid): calls["approve"] += 1
    def receipt(pid): calls["receipt"] += 1; return "rcpt_1"
    def tunnel(): calls["tunnel"] += 1; return ("https://web.x", "https://api.x")
    return ExposeDeps(require_auth=lambda: auth, create_permission=create,
                      approve_permission=approve, write_receipt=receipt, start_tunnel=tunnel), calls


def test_fail_closed_when_auth_off_and_not_overridden():
    deps, calls = _deps(auth=False)
    r = request_expose(owner_auto_approve=False, allow_insecure=False, deps=deps)
    assert r.ok is False and "authentication" in r.message.lower()
    assert calls["create"] == 0 and calls["tunnel"] == 0


def test_allow_insecure_overrides_auth_off():
    deps, calls = _deps(auth=False)
    r = request_expose(owner_auto_approve=True, allow_insecure=True, deps=deps)
    assert r.ok is True and calls["tunnel"] == 1


def test_explicit_request_creates_permission_but_no_tunnel_until_approved():
    deps, calls = _deps()
    r = request_expose(owner_auto_approve=False, allow_insecure=False, deps=deps)
    assert r.ok is True and r.tunnel_started is False
    assert calls["create"] == 1 and calls["approve"] == 0 and calls["tunnel"] == 0
    assert r.permission_id == "perm_1" and "approve" in r.message


def test_lecture_owner_auto_approves_with_receipt_and_tunnel():
    deps, calls = _deps()
    r = request_expose(owner_auto_approve=True, allow_insecure=False, deps=deps)
    assert r.ok is True and r.tunnel_started is True
    assert calls["create"] == 1 and calls["approve"] == 1 and calls["receipt"] == 1 and calls["tunnel"] == 1
    assert r.receipt_id == "rcpt_1" and r.web_url == "https://web.x" and r.api_url == "https://api.x"


@pytest.mark.asyncio
async def test_request_session_permission_persists_pending():
    """The real integration (un-mocked): a session.expose request becomes a visible PENDING
    permission a human can approve. (No worker command is enqueued — that's a review gate,
    guaranteed by policy.classify(session.expose)=require_human_approval ∉ _EXECUTABLE.)"""
    from app.services import control_plane
    pid = await control_plane.request_session_permission("Expose this Dipeen workspace over a public tunnel")
    perms = control_plane.list_permissions(status="requested")
    match = [p for p in perms if p.permission_request_id == pid]
    assert match and match[0].action == "session.expose" and match[0].state == "requested"
