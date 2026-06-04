"""Dipeen's first capabilities: workspace.open / workspace.status / team.invite.

Thin async handlers over control_plane + the teams invite API. Registered into the catalog.
session.expose / session.close live in Plan B.
"""
from __future__ import annotations

import os

from app.services import control_plane

from .capability_catalog import Capability, CapabilityResult, register


async def mint_invite(team_id: str) -> dict:
    """Mint a fresh invite (wraps control_plane.mint_team_invite, added in Task 6).
    Patched in tests."""
    return await control_plane.mint_team_invite(team_id)


async def _cap_team_invite(ctx: dict, params: dict) -> CapabilityResult:
    inv = await mint_invite(ctx["team_id"])
    code, api = inv["code"], ctx.get("api_url", "http://localhost:8000")
    return CapabilityResult(
        ok=True, message=f"Invite code {code} (expires {inv['expires_at']}).",
        next_actions=[f"/dipeen join {code}", f"dipeen-agent join {code} --api-url {api}"],
        data={"invite_code": code, "expires_at": inv["expires_at"]})


async def _cap_workspace_status(ctx: dict, params: dict) -> CapabilityResult:
    workers = control_plane.list_workers()
    online = sum(1 for w in workers if w.state == "online")
    running = sum(1 for c in await control_plane.list_commands() if c.state in ("leased", "running"))
    pending = len(control_plane.list_permissions(status="requested"))
    return CapabilityResult(
        ok=True,
        message=f"{online} worker(s) online · {running} task(s) running · {pending} awaiting approval.",
        data={"workers_online": online, "running": running, "pending_permissions": pending})


async def _cap_workspace_open(ctx: dict, params: dict) -> CapabilityResult:
    inv = await mint_invite(ctx["team_id"])
    code, api = inv["code"], ctx.get("api_url", "http://localhost:8000")
    return CapabilityResult(
        ok=True, message="Dipeen workspace is open.",
        next_actions=["/dipeen expose this session", "/dipeen invite teammate",
                      f"dipeen-agent join {code} --api-url {api}"],
        data={"invite_code": code, "expires_at": inv["expires_at"]})


async def do_expose(*, owner_auto_approve: bool, allow_insecure: bool):
    """Capability-side expose = create a PENDING permission request (no tunnel — the API
    can't start a host-local tunnel). The host CLI (dipeen open lecture) does auto-approve+tunnel."""
    from app.services.session_expose import ExposeResult
    require_auth = os.environ.get("DIPEEN_REQUIRE_AUTH", "").lower() in ("1", "true", "yes")
    if not require_auth and not allow_insecure:
        return ExposeResult(ok=False, tunnel_started=False,
            message="Refusing to expose with authentication disabled. Enable DIPEEN_REQUIRE_AUTH "
                    "or use --allow-insecure-tunnel on the host.")
    pid = await control_plane.request_session_permission("Expose this Dipeen workspace over a public tunnel")
    return ExposeResult(ok=True, permission_id=pid, tunnel_started=False,
        message=f"Expose requested — approve to open the public link: /dipeen approve {pid}")


async def _cap_session_expose(ctx: dict, params: dict):
    res = await do_expose(owner_auto_approve=False, allow_insecure=False)
    actions = [f"/dipeen approve {res.permission_id}"] if res.permission_id else []
    return CapabilityResult(ok=res.ok, message=res.message, next_actions=actions,
                            data={"permission_id": res.permission_id})


async def _cap_session_close(ctx: dict, params: dict):
    return CapabilityResult(ok=True, message="Close the public tunnel from the host: dipeen close. "
                            "Dipeen HQ stays running.", next_actions=["dipeen close"])


def register_dipeen_capabilities() -> None:
    register(Capability("workspace.open", "Open workspace", _cap_workspace_open))
    register(Capability("workspace.status", "Workspace status", _cap_workspace_status))
    register(Capability("team.invite", "Invite teammate", _cap_team_invite))
    register(Capability("session.expose", "Expose session", _cap_session_expose))
    register(Capability("session.close", "Close session", _cap_session_close))
