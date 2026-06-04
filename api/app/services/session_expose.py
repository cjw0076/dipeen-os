"""session.expose — public exposure as a Permissioned Action (deterministic, DI).

Fail-closed on auth. Create a PermissionRequest; lecture (owner) auto-approves with a
receipt and starts the tunnel; otherwise the request stays pending until /dipeen approve.
The HOST process is the executor (it holds cloudflared) — Core executes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ExposeDeps:
    require_auth: Callable[[], bool]
    create_permission: Callable[[], str]          # -> permission_id
    approve_permission: Callable[[str], None]
    write_receipt: Callable[[str], str]           # -> receipt_id
    start_tunnel: Callable[[], tuple[str, str]]   # -> (web_url, api_url)


@dataclass
class ExposeResult:
    ok: bool
    message: str
    permission_id: Optional[str] = None
    receipt_id: Optional[str] = None
    web_url: Optional[str] = None
    api_url: Optional[str] = None
    tunnel_started: bool = False


def request_expose(*, owner_auto_approve: bool, allow_insecure: bool, deps: ExposeDeps) -> ExposeResult:
    if not deps.require_auth() and not allow_insecure:
        return ExposeResult(
            ok=False, tunnel_started=False,
            message=("Refusing to expose with authentication disabled.\n"
                     "Enable it (recommended) or override explicitly:\n"
                     "  dipeen open --tunnel --require-auth\n"
                     "  dipeen open --tunnel --allow-insecure-tunnel"))
    pid = deps.create_permission()
    if not owner_auto_approve:
        return ExposeResult(ok=True, permission_id=pid, tunnel_started=False,
                            message=f"Expose requested — approve to open the public link: /dipeen approve {pid}")
    deps.approve_permission(pid)
    receipt = deps.write_receipt(pid)
    web, api = deps.start_tunnel()
    return ExposeResult(ok=True, permission_id=pid, receipt_id=receipt, web_url=web, api_url=api,
                        tunnel_started=True,
                        message=f"Public access requested and approved for this session (receipt {receipt}).")
