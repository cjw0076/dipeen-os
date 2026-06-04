"""Render OpenSessionResult to the action-centric terminal output. Formatting only."""
from __future__ import annotations

from .open_session import OpenSessionResult


def format_open_local(r: OpenSessionResult) -> str:
    return (
        "Dipeen workspace is open.\n\n"
        f"Workspace:    {r.team_name}\n"
        f"Invite code:  {r.invite_code}   (expires {r.invite_expires_at})\n\n"
        "Next actions:\n"
        "  /dipeen expose this session          (public link — asks for your approval)\n"
        "  /dipeen invite teammate\n"
        '  /dipeen assign cap:claude "review the README"\n\n'
        "Local Control Tower:\n"
        f"  {r.web_url}\n"
    )
