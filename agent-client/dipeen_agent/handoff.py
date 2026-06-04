"""Handoff Runner (Agent CLI Harness v1 — semi-auto, demo-safe).

Closes the meeting→evidence loop *without* auto-running anyone's CLI:

    dipeen-agent task next                         # lease the command Dipeen assigned to me
    dipeen-agent task prompt <id> --runner claude  # render its prompt → .dipeen/prompts/<runner>/<id>.md
    # ... the human runs their own Claude/Codex on that prompt, writes result.md ...
    dipeen-agent task submit <id> --from-file result.md   # submit summary + git diff as evidence

It speaks the existing worker endpoints over plain HTTP (register / poll / result) — it does NOT
drive WorkerHttpClient / WorkerNode / the runner-adapter layer (those are a separate, auto-run effort).
Core never executes a provider; the human's local agent does, and Dipeen records the evidence.

`render_prompt` and `capture_git_evidence` are pure (no network/config) so they unit-test cleanly.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx

_DIR = Path(".dipeen")
_DEFAULT_CAPS = ["provider.claude", "provider.codex", "workspace.write"]


# ──────────────────────── pure: prompt rendering + evidence capture ────────────────────────
def render_prompt(command: dict[str, Any], runner: str) -> str:
    """A leased command → a copy-paste prompt for the human's local agent. Mirrors the
    PromptEnvelope shape in plain Markdown: objective, context, workspace, safety, evidence."""
    task = command.get("task") or {}
    cid = command.get("command_id", "?")
    title = task.get("title") or command.get("command_type") or "task"
    objective = task.get("intent") or title
    workspace = command.get("workspace_ref") or command.get("workspace_root") or "(your current repo)"
    repo = command.get("repo") or "—"
    caps = ", ".join(command.get("required_capabilities") or []) or "—"
    accept = task.get("acceptance") or []
    accept_lines = "\n".join(f"  - {a.get('type', a)}: {a.get('artifact_type', '')}".rstrip(": ")
                             for a in accept) or "  - (none specified)"
    return f"""# Dipeen task for {runner}

**Command:** `{cid}`   ·   **Task:** {title}

## Objective
{objective}

## Context
- Provider requested: {command.get('provider') or runner}
- Required capabilities: {caps}
- Acceptance:
{accept_lines}

## Workspace
- {workspace}   (repo: {repo})

## Safety policy — dry-run by default
- Do **not** push, deploy, open PRs, delete files, or touch secrets.
- For any such action, STOP and request permission through Dipeen — don't do it yourself.

## What to return (evidence)
1. Do the work in this workspace; leave code changes in the working tree (don't commit/push).
2. Write a short summary of what you did / found to a file, e.g. `result.md`.
3. Submit — `dipeen-agent task submit {cid} --from-file result.md` — which attaches your
   summary **and the `git diff`** as evidence. Dipeen verifies the evidence; "done" is a claim.
"""


def capture_git_evidence(workspace: str) -> tuple[list[str], str]:
    """(changed_files, unified_diff) for the workspace — tracked edits + untracked new files.
    Returns ([], "") if it isn't a git repo or git is unavailable (no crash)."""
    def _git(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20)   # Windows: avoid cp949 decode
            return r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    changed = [ln.strip() for ln in _git("diff", "--name-only").splitlines() if ln.strip()]
    untracked = [ln.strip() for ln in _git("ls-files", "--others", "--exclude-standard").splitlines() if ln.strip()]
    for f in untracked:
        if f not in changed:
            changed.append(f)
    return changed, _git("diff")


# ──────────────────────── local lease state (between next/prompt/submit) ────────────────────────
def _lease_path(command_id: str) -> Path:
    return _DIR / "leases" / f"{command_id}.json"


def _save_lease(command_id: str, state: dict) -> None:
    p = _lease_path(command_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_lease(command_id: str) -> dict | None:
    p = _lease_path(command_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _caps(raw: str | None) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()] if raw else list(_DEFAULT_CAPS)


# ──────────────────────── HTTP orchestration (existing endpoints only) ────────────────────────
async def _next(capabilities: str | None) -> int:
    from dipeen_agent.config import API_URL, AGENT_ID, DIPEEN_TOKEN
    caps = _caps(capabilities)
    team_hdr = {"Authorization": f"Bearer {DIPEEN_TOKEN}"} if DIPEEN_TOKEN else {}
    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as c:
        try:
            reg = (await c.post("/api/workers", json={"worker_id": AGENT_ID or "handoff",
                                                      "capabilities": caps}, headers=team_hdr)).json()
            wid, wtok = reg["worker_id"], reg["worker_token"]
            poll = (await c.post(f"/api/workers/{wid}/commands/poll", json={"capabilities": caps},
                                 headers={"Authorization": f"Bearer {wtok}"})).json()
        except (httpx.ConnectError, httpx.TimeoutException):
            print(f"Can't reach Dipeen at {API_URL}. Open the workspace and try again.")
            return 1
        except (KeyError, json.JSONDecodeError):
            print("Dipeen didn't accept the worker — check your invite/auth and try again.")
            return 1
    cmd = poll.get("command")
    if not cmd:
        print("No work is assigned to you right now.")
        return 0
    _save_lease(cmd["command_id"], {"worker_id": wid, "worker_token": wtok,
                                    "lease_id": poll.get("lease_id"), "command": cmd, "api_url": API_URL})
    title = (cmd.get("task") or {}).get("title") or cmd.get("command_type")
    print(f"Leased task {cmd['command_id']} — {title}")
    print(f"  Next: dipeen-agent task prompt {cmd['command_id']} --runner claude")
    return 0


def _prompt(command_id: str, runner: str) -> int:
    state = _load_lease(command_id)
    if not state:
        print(f"No leased command {command_id}. Run:  dipeen-agent task next")
        return 1
    path = _DIR / "prompts" / runner / f"{command_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_prompt(state["command"], runner), encoding="utf-8")
    print(f"Prompt ready: {path}")
    print(f"  Run {runner} on it, save your result to result.md, then:")
    print(f"  dipeen-agent task submit {command_id} --from-file result.md")
    return 0


async def _submit(command_id: str, from_file: str, workspace: str | None) -> int:
    from dipeen_agent.config import API_URL
    state = _load_lease(command_id)
    if not state:
        print(f"No leased command {command_id}. Run:  dipeen-agent task next")
        return 1
    fp = Path(from_file)
    summary = fp.read_text(encoding="utf-8") if fp.exists() else from_file
    ws = workspace or (state.get("command", {}).get("workspace_root") or ".")
    changed, diff = capture_git_evidence(ws)
    if diff:
        ep = _DIR / "evidence" / f"{command_id}.diff"
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text(diff, encoding="utf-8")
    body = {"status": "done", "summary": summary[:4000], "changed_files": changed,
            "runner": "handoff", "lease_id": state.get("lease_id")}
    wid, wtok = state["worker_id"], state["worker_token"]
    async with httpx.AsyncClient(base_url=state.get("api_url", API_URL), timeout=30) as c:
        try:
            r = await c.post(f"/api/workers/{wid}/commands/{command_id}/result", json=body,
                             headers={"Authorization": f"Bearer {wtok}"})
        except (httpx.ConnectError, httpx.TimeoutException):
            print("Can't reach Dipeen to submit. Try again in a moment.")
            return 1
    if r.status_code == 409:
        print("This task was re-assigned (your lease expired). Run:  dipeen-agent task next")
        return 1
    if r.status_code != 200:
        print("Couldn't submit — the task may be gone or no longer assigned to you.")
        return 1
    state_label = r.json().get("state", "recorded")
    print(f"Submitted {command_id}: {len(changed)} changed file(s) + summary. Dipeen will verify it (state: {state_label}).")
    return 0


async def run(args) -> int:
    if args.task_command == "next":
        return await _next(getattr(args, "capabilities", None))
    if args.task_command == "prompt":
        return _prompt(args.command_id, args.runner)
    if args.task_command == "submit":
        return await _submit(args.command_id, args.from_file, getattr(args, "workspace", None))
    print("Usage: dipeen-agent task {next|prompt <id>|submit <id> --from-file result.md}")
    return 1
