"""Control intent endpoint (ux-command-layer-v0) — one entry for slash + natural language.

POST /api/control/intent turns "/dipeen assign cap:codex fix README" (or plain prose from the
web prompt box) into a real action against the existing services, and answers in human words —
Workspace / Worker / Task / Evidence / Permission — never team_id, lease_id, or an HTTP code.
The CLI `dipeen-agent slash` and the web ⌘K palette / prompt box both POST here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.nat.core import capability_catalog
from app.nat.core.capability_catalog import get as get_capability
from app.nat.core.capabilities_dipeen import register_dipeen_capabilities
from app.nat.core.slash import SlashIntent, parse_slash, VERBS
from app.routers.auth import get_team_id
from app.services import control_plane

register_dipeen_capabilities()                    # idempotent — capability catalog for open/invite

router = APIRouter()

_VERB_TO_CAP = {"open": "workspace.open", "invite": "team.invite",
                "expose": "session.expose", "close": "session.close"}
_CAP_TO_VERB = {cap: verb for verb, cap in _VERB_TO_CAP.items()}

# Curated verbs handled directly in /intent (not in the capability catalog). Each is a runnable
# slash template the ⌘K palette renders; needs_input=True means the user finishes typing first.
#   (id, human label, slash template, needs_input)
_PALETTE_VERBS = (
    ("status", "Status — workers online, tasks running, approvals waiting", "/dipeen status", False),
    ("workers", "Workers — who has joined and their capabilities", "/dipeen workers", False),
    ("permissions", "Permissions — actions awaiting approval", "/dipeen permissions", False),
    ("ask", "Ask the team to do something", "/dipeen ask ", True),
    ("assign", "Assign work to a capability, role, or teammate", "/dipeen assign cap:claude ", True),
    ("approve", "Approve a proposal or permission by id", "/dipeen approve ", True),
    ("deny", "Reject a proposal or permission by id", "/dipeen deny ", True),
)

_PREFIXES = ("/dipeen", "/dp", "dipeen ")


class IntentBody(BaseModel):
    text: str = Field(..., description='Slash command or natural language, e.g. /dipeen ask "fix README"')
    room_id: str = "general"


class PaletteCommand(BaseModel):
    id: str
    label: str
    template: str            # ready-to-run slash text the palette submits to /api/control/intent
    needs_input: bool = False


@router.get("/capabilities")
async def control_capabilities() -> dict:
    """The ⌘K palette source: curated verbs + the capability catalog, as runnable templates."""
    cmds = [PaletteCommand(id=i, label=l, template=t, needs_input=n) for (i, l, t, n) in _PALETTE_VERBS]
    if not capability_catalog.catalog():              # self-heal if test isolation cleared the registry
        register_dipeen_capabilities()
    for cap in capability_catalog.catalog():
        verb = _CAP_TO_VERB.get(cap.name)
        if verb and "web" in cap.surfaces:
            cmds.append(PaletteCommand(id=cap.name, label=cap.human_label, template=f"/dipeen {verb}"))
    return {"commands": [c.model_dump() for c in cmds]}


def _to_intent(text: str) -> SlashIntent:
    """Slash text → parsed intent. Bare prose (web prompt box) → an `ask` for the team."""
    s = (text or "").strip()
    if s.lower().startswith(_PREFIXES):
        return parse_slash(s)
    if not s:
        return SlashIntent(verb="", error='Type a request, e.g. "fix the README Quick Start".')
    return SlashIntent(verb="ask", body=s, raw=s)            # prompt box = natural language ask


def _target_label(target: dict | None) -> str:
    if not target or target["kind"] == "any":
        return "any available teammate"
    return {"worker": "@", "cap": "a ", "role": "the "}.get(target["kind"], "") + target["value"] + \
        ({"cap": "-capable worker", "role": " team"}.get(target["kind"], ""))


def _plan_step(intent: SlashIntent) -> dict:
    """assign/ask intent → a one-step proposal plan (provider + optional assignment)."""
    step: dict = {"intent": intent.body, "provider": "claude"}
    t = intent.target
    if t and t["kind"] == "cap":
        step["provider"] = t["value"]
    elif t and t["kind"] == "role":
        step["assignment"] = {"role": t["value"]}
    elif t and t["kind"] == "worker":
        step["assignment"] = {"preferred_worker": t["value"]}
    return step


def _ok(verb: str, message: str, **data) -> dict:
    return {"ok": True, "verb": verb, "message": message, "data": data or None}


@router.post("/intent")
async def control_intent(body: IntentBody, team_id: str = Depends(get_team_id)):
    intent = _to_intent(body.text)
    if intent.error:
        return {"ok": False, "verb": intent.verb, "message": intent.error, "data": None}
    v, by = intent.verb, f"user://{team_id}"

    if v == "status":
        workers = control_plane.list_workers()
        online = sum(1 for w in workers if w.state == "online")
        running = sum(1 for c in control_plane.list_commands() if c.state in ("leased", "running"))
        pending = len(control_plane.list_permissions(status="requested"))
        return _ok(v, f"{online} worker(s) online · {running} task(s) running · {pending} awaiting approval.",
                   workers_online=online, running=running, pending_permissions=pending)

    if v == "workers":
        workers = control_plane.list_workers()
        lines = [f"{'●' if w.state == 'online' else '○'} {w.worker_id} — "
                 f"{', '.join(w.capabilities) or 'no capabilities'}" for w in workers]
        return _ok(v, "\n".join(lines) or "No workers have joined yet.",
                   workers=[w.model_dump(mode="json") for w in workers])

    if v == "permissions":
        perms = control_plane.list_permissions(status="requested")
        lines = [f"{p.permission_request_id}  {p.action} → {p.target}  "
                 f"(approve: /dipeen approve {p.permission_request_id})" for p in perms]
        return _ok(v, "\n".join(lines) or "No permissions are awaiting approval.",
                   permissions=[p.permission_request_id for p in perms])

    if v in ("ask", "assign"):
        if not intent.body:
            return {"ok": False, "verb": v, "message": "Tell Dipeen what to do.", "data": None}
        props = control_plane.propose_plan([_plan_step(intent)], room_id=body.room_id, proposed_by=by)
        p = props[0]
        who = _target_label(intent.target) if v == "assign" else "the team"
        return _ok(v, f"Proposed task “{intent.body}” for {who}. Approve to dispatch: "
                      f"/dipeen approve {p.proposal_id}", proposal_id=p.proposal_id, task=intent.body)

    if v == "approve":
        cmd = control_plane.confirm_proposal(intent.arg, decided_by=by)
        if cmd:
            title = cmd.task.title if cmd.task else intent.arg
            return _ok(v, f"Dispatched “{title}” — a capable worker will pick it up.", command_id=cmd.command_id)
        res = control_plane.approve_permission(intent.arg, decided_by=by)
        if res.get("permission"):
            note = " A worker will run it (dry-run unless local execution is enabled)." if res.get("command") else ""
            return _ok(v, f"Permission approved.{note}", command_id=(res["command"].command_id if res.get("command") else None))
        return {"ok": False, "verb": v,
                "message": f"Nothing to approve for ‘{intent.arg}’ — it may be already decided or not found.",
                "data": None}

    if v == "deny":
        prop = control_plane.reject_proposal(intent.arg, decided_by=by)
        if prop:
            return _ok(v, f"Rejected “{prop.intent}” — it will not be dispatched.", proposal_id=prop.proposal_id)
        perm = control_plane.reject_permission(intent.arg, decided_by=by)
        if perm:
            return _ok(v, "Permission denied — no action will run.",
                       permission_request_id=perm.permission_request_id)
        return {"ok": False, "verb": v,
                "message": f"Nothing to reject for ‘{intent.arg}’ — it may be already decided or not found.",
                "data": None}

    cap_name = _VERB_TO_CAP.get(v)
    cap = get_capability(cap_name) if cap_name else None
    if cap_name and cap is None:                  # self-heal if the global catalog was cleared (e.g. test isolation)
        register_dipeen_capabilities()
        cap = get_capability(cap_name)
    if cap:
        ctx = {"team_id": team_id, "decided_by": by,
               "api_url": "http://localhost:8000", "room_id": body.room_id}
        res = await cap.handler(ctx, {})
        return {"ok": res.ok, "verb": v, "message": res.message,
                "data": {**(res.data or {}), "next_actions": res.next_actions}}

    if v == "join":
        return _ok(v, f"A teammate joins with:  dipeen-agent join {intent.arg}", code=intent.arg)
    return _ok(v, f"‘{v}’ isn’t wired in v0 yet — try: ask, assign, approve, status, workers, permissions.")
