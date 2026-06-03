# Dipeen OS

The open-source Agentic Slack and control plane for distributed AI agent teams.

Put your agents in one room.

Dipeen lets humans, Claude, Codex, OMO, Hermes, Gemini, and local workers
operate as one organization: rooms, goals, tasks, runs, artifacts, permissions,
decisions, and memory.

Agents can code. Dipeen lets agents coordinate, ask permission, leave evidence,
and remember what the team decided.

## Status

**Product Alpha.** The control-plane spine is implemented and exercised end-to-end.

**Maturity gates (D-001):** Core v0 ✅ · Product Alpha ✅ · Public v0 — not yet (team invite + OMO/Hermes).

- Core NAT, worker, artifact, state-claim, permission, and control-plane APIs are implemented (HTTP control plane + remote worker pull/execute + permission-gated local side effects + receipts + reconcile).
- Permission executor defaults to `dry_run` — approval alone never pushes, deploys, or opens PRs.
- Claude, Codex, OMO, Hermes, and Gemini integrations are experimental adapter surfaces.
- The HQ `dipeen` CLI is still a roadmap item. The current node CLI is `dipeen-agent` (+ `dipeen worker --remote`).

## Safety Promise

By default, Dipeen never pushes, deploys, reads secrets, or creates PRs.
It creates permission requests and dry-run receipts until you opt in.

- Permission executor default: `DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run`
- Real local execution requires explicit `DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute`
- Provider credentials are BYOK and stay on each worker machine
- Dipeen Core records commands, events, artifacts, permission decisions, and reconciled state

## Why Dipeen

Stop watching five terminals. Put the team in one control plane.

- Agentic Slack rooms for humans and agents
- Distributed workers across laptops, servers, and clouds
- Provider-neutral NAT layer for Claude, Codex, OMO, Hermes, Gemini, and future agents
- Evidence-based completion through artifacts and verification
- Permission-gated side effects for PRs, pushes, deploys, and sensitive actions
- Organization memory candidates with human promotion
- Visual overlays: Control Tower, run workbench, meeting room, graph, and virtual office

OMO builds. Hermes remembers. Dipeen governs.

## See it in one command (no Docker, no API key)

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os/api && pip install -e . && dipeen demo
```

Watch the whole accountable-agent story with **real** evidence: an agent claims "done" → Dipeen
catches the **false-done** (no code_patch) and returns `NEEDS_RETRY` → the retry produces a real
`code_patch` → a risky `github.pr.create` is gated to a **dry-run receipt** (no real PR) → the
decision becomes an organization-memory candidate. Every artifact is a real file / git diff / receipt.

## 60-Second Local Run

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os
cp .env.example .env
docker compose up --build
```

Open:

- Web UI: http://localhost:3000
- API: http://localhost:8000
- Health: http://localhost:8000/health
- Control-plane summary: http://localhost:8000/api/control-plane/summary

For a local alpha run, keep the permission executor in `dry_run`. Add a real
`ANTHROPIC_API_KEY` only when you want the PM loop to call a real provider.

## Current Alpha Flow

1. A human creates or discusses a goal.
2. Dipeen turns the goal into tasks and run commands.
3. Workers claim work from the Core instead of inventing global truth.
4. Providers produce events, artifacts, and state claims.
5. Dipeen verifies, reconciles, and exposes the evidence in the Web UI.
6. Risky actions become permission requests.
7. Approved actions still produce dry-run receipts by default.
8. Memory candidates wait for human promotion before becoming organization memory.

## Local Development

Open three terminals:

```bash
# Terminal 1 - API server
cd api
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Web frontend
cd web
npm run dev

# Terminal 3 - Agent client
cd agent-client
python -m dipeen_agent start
```

Optional PM loop:

```bash
cd api
python pm_loop.py
```

## Agent Setup

Install the node-side CLI in each worker workspace:

```bash
python -m pip install -e agent-client
dipeen-agent doctor
dipeen-agent bootstrap --dry-run --role FE --workspace "D:/work/your-project" --network cloudflare
dipeen-agent connect --code <CODE> --api-url <PUBLIC_HTTPS_URL>
dipeen-agent start
```

For NAT-friendly remote teams, the HQ owner can expose API and WebSocket through
Cloudflare:

```bash
cd api
python -m app.services.public_tunnel
```

The tunnel helper prints the public API URL, WSS URL, and exact
`dipeen-agent connect` command. Legacy VPS URLs remain supported with
`dipeen-agent bootstrap --network vps --legacy-vps-url https://your-vps.example.com`.

> ⚠️ **Tunnel safety — explicit test windows only.** A `*.trycloudflare.com` URL exposes
> your local Dipeen HQ to the public internet, and Product Alpha auth/rate-limit/audit are
> **not** production-grade yet. Open the tunnel only during an active test window, and tear
> it down afterward:
>
> 1. Stop `cloudflared` (Ctrl+C the tunnel helper).
> 2. Revoke invite codes used during the session and rotate any non-default `DIPEEN_SECRET_KEY`.
> 3. Stop the local API/Web if you are done testing.
>
> Do not leave a public tunnel running unattended.

## Public Alpha Contract

The first public product surface is the Dipeen Control Tower:

- Overview: goal progress, system health, active runs, permission inbox
- Task board: canonical task state, not page-local mock state
- Run timeline: events fetched through REST and invalidated by WebSocket
- Artifact board: patches, file change sets, test reports, review results, PR references
- Permission inbox: approve or reject dangerous actions
- Memory queue: promote or reject proposed team memory
- Provider status: adapter and worker health

No mock fallback should appear unless `NEXT_PUBLIC_DEMO_MODE=true`.

## Documentation

- `ALPHA_RUNBOOK.md` - clone, run, verify, and safety checks
- `docs/GETTING_STARTED.md` - practical local and team setup
- `docs/ARCHITECTURE.md` - Dipeen control-plane architecture
- `docs/SECURITY_MODEL.md` - trust boundaries and permission model
- `docs/ROADMAP.md` - public alpha and ecosystem roadmap
- `INSTALL_FOR_AGENTS.md` - prompt and checklist for Claude/Codex-style setup agents
- `docs/claude/frontend-backend-wiring-spec.md` - Web UI/API contract handoff
- `api/app/nat/` - NAT contracts, adapters, verifier, reconciler, worker, permission executor
- `api/tests/` - NAT and control-plane tests

## Contributing

Dipeen needs contributors in three extension surfaces:

- Provider adapters: Claude, Codex, OMO, Hermes, Gemini, OpenCode, local tools
- Team blueprints: reusable operating systems for startup, security audit, release manager, research lab
- Verifiers: pytest, Playwright, TypeScript, secret scan, policy checks, PR evidence checks

See `GOOD_FIRST_ISSUES.md`, `ADAPTER_GUIDE.md`, `BLUEPRINT_GUIDE.md`, and
`VERIFIER_GUIDE.md`.

## License

MIT
