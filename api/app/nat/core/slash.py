"""Slash command grammar v0 (ux-command-layer-v0) — pure parser, test-first.

    /dipeen <verb> [target] [body...]

The one surface a teammate types — in a CLI, a chat box, or a terminal. The grammar hides
team_id / lease_id / worker JWT / CORS: the user speaks Workspace / Worker / Task / Evidence /
Permission, and errors come back in plain language, never HTTP codes. Parsing is pure (no DB,
no I/O); execution + human-friendly rendering live in the /api/control/intent endpoint.

target (assign):  @worker | cap:codex|claude|omo | role:fe|pm | any
"""
from __future__ import annotations

from pydantic import BaseModel

VERBS = {"open", "invite", "status", "join", "workers", "ask", "assign", "claim", "submit",
         "permissions", "approve", "deny", "artifacts", "stop", "expose", "close"}
_PREFIXES = ("/dipeen", "/dp", "dipeen")          # tolerate a few leading forms
_NEEDS_ID = {"join", "approve", "deny"}           # verbs that require an id/code arg
_NO_ARG = {"open", "invite", "status", "workers", "permissions", "stop", "close"}


class SlashIntent(BaseModel):
    """Parsed intent. ``error`` (when set) is user-language — render it as-is, no HTTP code."""
    verb: str
    target: dict | None = None     # assign: {"kind": "worker"|"cap"|"role"|"any", "value": str}
    arg: str | None = None         # join code / approve id / task id
    body: str = ""                 # free-text request (ask / assign)
    raw: str = ""
    error: str | None = None       # None = parsed OK


def _parse_target(tok: str) -> dict | None:
    if tok == "any":
        return {"kind": "any", "value": "any"}
    if tok.startswith("@") and len(tok) > 1:
        return {"kind": "worker", "value": tok[1:]}
    if tok.startswith("cap:") and len(tok) > 4:
        return {"kind": "cap", "value": tok[4:]}
    if tok.startswith("role:") and len(tok) > 5:
        return {"kind": "role", "value": tok[5:]}
    return None


def parse_slash(text: str) -> SlashIntent:
    raw = (text or "").strip()
    s = raw
    for p in _PREFIXES:
        if s.lower() == p or s.lower().startswith(p + " "):
            s = s[len(p):].strip()
            break
    if not s:
        return SlashIntent(verb="", raw=raw, error='Type a command, e.g. /dipeen ask "fix the README"')

    parts = s.split(maxsplit=1)
    verb = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if verb not in VERBS:
        return SlashIntent(verb=verb, raw=raw,
                           error=f"Unknown command '{verb}'. Try: ask, assign, approve, status, workers, join.")

    if verb == "assign":
        tparts = rest.split(maxsplit=1)
        target = _parse_target(tparts[0]) if tparts else None
        if target is None:
            return SlashIntent(verb=verb, raw=raw,
                               error='assign needs a target: @worker, cap:codex, role:fe, or any — '
                                     'e.g. /dipeen assign cap:codex "fix the README"')
        body = tparts[1].strip() if len(tparts) > 1 else ""
        if not body:
            return SlashIntent(verb=verb, target=target, raw=raw, error="assign needs a task description.")
        return SlashIntent(verb=verb, target=target, body=body, raw=raw)

    if verb == "ask":
        if not rest:
            return SlashIntent(verb=verb, raw=raw, error='ask needs a request, e.g. /dipeen ask "fix the README"')
        return SlashIntent(verb=verb, body=rest, raw=raw)

    if verb == "expose":
        # `expose this session` — free-text body, optional (no error even when empty)
        return SlashIntent(verb=verb, body=rest, raw=raw)

    if verb in _NEEDS_ID or verb in ("claim", "submit", "artifacts"):
        arg = rest.split(maxsplit=1)[0] if rest else None
        body = rest[len(arg):].strip() if (arg and verb == "claim") else ""
        if verb in _NEEDS_ID and not arg:
            return SlashIntent(verb=verb, raw=raw, error=f"{verb} needs an id/code, e.g. /dipeen {verb} 12")
        return SlashIntent(verb=verb, arg=arg, body=body, raw=raw)

    # open / status / workers / permissions / stop — no args
    return SlashIntent(verb=verb, raw=raw)
