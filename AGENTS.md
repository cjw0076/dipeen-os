# AGENTS.md — onboarding contract for AI agents

You are an AI agent (Claude, Codex, Cursor, …) asked to **set up Dipeen** for a human.
Dipeen is the open-source **control plane for accountable AI agent teams**: humans and agents
share rooms, work is routed to the right worker, results are verified by evidence, risky actions
are gated by permission, and decisions become organization memory.

**Safety first — this never changes:**
- Permission executor defaults to `dry_run`. Dipeen **never** pushes, deploys, opens PRs, or reads
  secrets unless a human explicitly opts in (`DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute`).
- The Core executes nothing. Workers run provider CLIs **locally** with the human's own keys (BYOK).
- A public Cloudflare tunnel exposes the local HQ — open it only during an explicit test window.

Pick the path that matches the request.

---

## Path A — Run the HQ (control plane + web UI)

The HQ holds the command queue, event log, artifacts, permissions, and the web Control Tower.

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os
cp .env.example .env
# keep dev-safe defaults: DIPEEN_DEBUG=true, DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run
docker compose up --build
```

Verify (do not declare success without this):

```bash
curl -fsS http://localhost:8000/health                       # {"status":"ok",...}
curl -fsS http://localhost:8000/api/control-plane/summary    # JSON summary
# Web Control Tower: http://localhost:3000
```

Want a 60-second, key-free proof of the whole flow first?

```bash
cd api && pip install -e . && dipeen demo
```

To let teammates on other machines join, mint an invite and (optionally) expose the HQ:

```bash
# create an invite code (team_id is "default-team" in dev)
curl -fsS -X POST http://localhost:8000/api/teams/default-team/invite     # → {"code": "...", ...}
# expose the local HQ publicly for an explicit test window (no account needed):
cd api && python -m app.services.public_tunnel                            # prints a public https URL
```

---

## Path B — Join as a worker (a teammate's machine)

The worker pulls commands it is capable of and runs the provider locally. The human must have a
provider CLI logged in (e.g. `claude`) or `ANTHROPIC_API_KEY` set.

**Fastest — one-touch (empty machine, no repo/Python needed).** The installer is thin: it sets up
`uv` + `dipeen-agent` only. Provider runtimes (e.g. `bun` for opencode) are installed by
`dipeen-agent setup` (runtime before runner); auth/BYOK stays manual. Details: `docs/INSTALL.md`.

```bash
# Unix (macOS/Linux): installs uv + dipeen-agent, then joins + starts a worker
curl -fsSL https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.sh \
  | sh -s -- "<HQ_PUBLIC_URL>/api/teams/join?code=<CODE>"
```
```powershell
# Windows (PowerShell): installs uv + dipeen-agent, then join
irm https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.ps1 | iex
dipeen-agent join "<HQ_PUBLIC_URL>/api/teams/join?code=<CODE>" --start-worker
```

**Manual (repo already cloned):**

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os
python -m pip install -e agent-client

dipeen-agent doctor                                          # check git/python/node/provider CLIs
# join the team with the invite code + public HQ url, then start a worker:
dipeen-agent connect --code <CODE> --api-url <HQ_PUBLIC_URL>
dipeen-agent worker --capabilities provider.claude,role.fe,workspace.write
```

Verify: the worker appears under **Worker Pool** in the HQ Control Tower, and
`curl <HQ_PUBLIC_URL>/api/control-plane/summary` lists it under `workers`.

---

## Capability convention → routing (important)

A command is delivered to a worker only when `command.required_capabilities ⊆ worker.capabilities`.
So **what you register as capabilities decides what work this machine receives.** Use namespaced tokens:

| token | meaning | example |
|---|---|---|
| `provider.<name>` | which provider this worker can run | `provider.claude`, `provider.codex` |
| `role.<role>` | the team role | `role.fe`, `role.be`, `role.qa` |
| `user.<name>` | a specific person | `user.minjun` |
| `repo.<slug>` | a checked-out repo | `repo.ezmap-web` |
| `workspace.write` | may modify the workspace | (grant for implementers) |

When a meeting assigns "minjun handles FE", Dipeen tags the command with `role.fe` (and/or
`user.minjun`); only a worker registered with those capabilities will lease it. Register accordingly:

```bash
dipeen-agent worker --capabilities provider.claude,role.fe,user.minjun,repo.ezmap-web,workspace.write
```

---

## Hard rules (do not violate)

- Do **not** set `DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute` unless the human explicitly asks.
- Do **not** leave a public tunnel running after a test window; stop `cloudflared` and revoke the invite.
- BYOK keys (`ANTHROPIC_API_KEY`, provider logins) stay on the worker machine — never send them to the HQ.
- Do not invent commands. If a step fails, run `dipeen-agent doctor` and report the actual output.

## More

- `ALPHA_RUNBOOK.md` — clone → run → verify, with the tunnel teardown checklist.
- `docs/GETTING_STARTED.md` · `docs/ARCHITECTURE.md` · `README.md` (Status + Safety Promise).
