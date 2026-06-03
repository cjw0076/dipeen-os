# Changelog

## [0.2.7] - 2026-06-03 — Coordinator (head agent), memory governance, support-level taxonomy

### Added
- **Coordinator — propose-only head agent.** `core/coordinator.py` decomposes a meeting into routed task
  candidates via an **injected** LLM (the worker runs its own provider with BYOK; the Core holds no key and
  calls no provider). It emits `ActionCandidate[]` only and **never** confirms — humans/policy stay the
  execution gate. Proven live: a real Claude run split a 3-message meeting into frontend/backend/qa tasks.
  (Design: a host-resident head agent would resurrect the retired pm_loop and break Core-executes-nothing / BYOK /
  human-approval — so the head is a worker-plane, propose-only role.)
- **Support-level taxonomy** — `docs/SUPPORT_LEVELS.md` + `support_levels.py`: `installed` ≠ `supported`.
  A provider is `advertised` (routable) only after a healthy live probe; `claude`/`codex` are `supported`,
  `omo`/`hermes` are `preview` until their live probe + CI are pinned.

### Changed / Fixed
- **Memory governance** — `close_meeting` now **persists** memory candidates to the review queue (they were
  generated and dropped). Still no auto-promotion: candidates are queued `pending` for a human to promote/reject.
- omo install guidance aligned to upstream (`bunx oh-my-openagent install`; not `npx/bunx omo`).
- New dev harnesses: `scripts/team_smoke.py` (keyless team cycle) and `scripts/team_test.py` (real claude+codex
  team cycle) — the §10 accountable-team loop, proven end-to-end.
- Internal dev version `0.2.7`; public alpha tag `v0.1.0-alpha`. Permission executor default remains `dry_run`.

## [0.2.6] - 2026-06-03 — Provider inspect polish, omo bun-link auto-fix, production UI

### Added
- **omo bun-link auto-fix.** `dipeen-agent doctor` detects when omo can't find Bun (`spawnSync bun ENOENT`) and offers `--fix` to set `BUN_BINARY`, so a freshly bootstrapped machine can run the omo provider without manual PATH surgery.
- **`providers inspect` shows provider details in the human view.** `team_mode` / `runtime` (omo) and `memory` / `skills` / `cron` (hermes) now print in the plain (non-`--json`) output.

### Changed
- Provider install / auth hints refined (omo: avoid the wrong `npx/bunx omo` package; hermes: `hermes model` for interactive provider/model selection).
- Web: production control-room UI cutover (ProductionViews, ControlTower, CommandCenter, KanbanBoard, AssignmentRouting) + spec-driven `useWorkspaceSpec` hook.
- Internal dev version `0.2.6`; public alpha tag `v0.1.0-alpha`.

## [0.2.5] - 2026-06-03 — Provider lifecycle (print-first) + OMO/Hermes NAT integration

### Added
- **Provider lifecycle — print-first opt-in install.** `dipeen providers install <name>` defaults to print-only (it shows the official upstream command and runs nothing); `--execute` is an explicit opt-in (dry-run preview → confirm → run → re-probe). `providers inspect` now separates `install_hint` (the provider *body*) from `runtime_deps` (e.g. omo→bun) and reports `capability_advertised`. A worker advertises `provider.X` **only after a live probe passes** — a missing or broken provider (e.g. omo without bun) leaves the worker online without that capability, so its tasks are never routed there. Bootstrap/`setup` auto-installs runtime deps but **never** auto-installs provider bodies or automates auth (BYOK stays on the worker).
- **OMO / Hermes provider discovery.** `providers inspect omo` surfaces `team_mode` (from config) and `runtime` (`~/.omo` teams/runs); `providers inspect hermes` surfaces `memory` / `skills` / `cron` (`~/.hermes`). Evidence-first: team_mode is reported off when unconfigured, memory usage is measured, gateway status is left unverified rather than assumed.
- **OMO / Hermes NAT integration (read-only mapping).** `adapters/{omo,hermes}.py` + provider inbound mapping: OMO team events / subtasks / diffs → Dipeen events / artifacts / state-claims (an OMO subtask is **not** a Dipeen Task); Hermes context retrieval → context evidence, memory/skill writes → MemoryCandidate / SkillCandidate (**never** auto-promoted to Organization Memory), cron → long-task. Boundaries enforced: the Core never executes a provider CLI; provider-local state stays provider-local.

### Changed
- Internal dev version `0.2.5`; public alpha tag `v0.1.0-alpha`. Permission executor default remains `dry_run`.

## [0.2.4] - 2026-06-03 — Keyless provider, team-flow, spec-driven UI

### Added
- **`provider.fake`** — keyless, deterministic provider (no API key, no network, no CLI). Workers can run the full loop (execute → real `code_patch` → verify → reconcile `DONE`) without any key — the answer to public-demo friction. All providers are CLI wrappers (`claude`/`codex`/`omo`/`hermes` = local CLI; `fake` = built-in); Dipeen holds no keys (BYOK is each CLI's own auth).
- **Assignment Routing + Routing Preview** — a meeting task is tagged with `role.*`/`user.*`/`repo.*`/`workspace.*`; only the assigned teammate's worker leases it. `POST /api/routing/preview` answers "who gets this work" (web `Assign Work` panel).
- **Workspace Registry** — commands carry `workspace_ref` (e.g. `workspace://ezmap-web`); each worker resolves it to its own local path. The HQ never knows a teammate's filesystem path.
- **Meeting Closure** — `POST /api/rooms/{id}/close` classifies room messages into decision / task / permission / memory / question candidates; only approved candidates become work.
- **TeamWorkspaceSpec** — host CLI configures the web UI by mode (`public_demo` / `team` / `production` / `debug`) via `.dipeen/workspace.yaml`; `GET /api/workspace/spec`. The web renders the spec's panels — change mode, not code.
- **One-touch onboarding** — `scripts/install.sh` / `install.ps1` (uv + dipeen-agent + join); `dipeen-agent join <url> --role FE --start-worker`.

### Changed
- Permission executor default remains `dry_run`. Internal dev version `0.2.4`; public alpha tag `v0.1.0-alpha`.

## [0.2.3] - 2026-06-03 — One-command demo, Assignment Routing, agent onboarding

### Added
- **`dipeen demo`** — keyless, deterministic Product Alpha walkthrough with **real** evidence: an agent claims "done" → Dipeen catches the false-done (`NEEDS_RETRY`) → the retry produces a real `code_patch` (`DONE`) → a risky PR is gated to a dry-run receipt → the decision becomes a memory candidate. New unified `dipeen` CLI entry (`[project.scripts]`).
- **Assignment Routing** — `AssignmentSpec` + `assignment_to_capabilities`: a confirmed meeting task is tagged with `role.*` / `user.*` / `repo.*` / `worker.*` capabilities, so **only the assigned teammate's worker leases it** (the HQ never pushes; workers pull what they're capable of). Backward compatible — no assignment means the provider pool.
- **`AGENTS.md`** — agent-delegated onboarding contract: an AI agent (Claude / Codex) can stand up the HQ or join a machine as a worker by reading it.
- **`dipeen-agent join <url> [--role FE] [--start-worker]`** — one-command new-device onboarding (connect + persist + optional worker start). `--role` maps to the `role.*` routing token.

### Changed
- README: one-command demo callout; `ALPHA_RUNBOOK`: instant demo path.

> Internal dev version `0.2.3`; public alpha tag `v0.1.0-alpha`. 191 API + 21 agent-client tests green.

## [0.2.2] - 2026-06-03 — M10.5 Release Hardening & Strangler Cutover

> Public-release surface for **Product Alpha** (maturity gate D-001: Core v0 ✅ · Product Alpha ✅ · Public v0 — not yet). Candidate for the `v0.1.0-alpha` public release.

### Added
- **local_execute 실측** — concrete `GitCommitExecutor` + `default_executors()`; approving `git.commit` now performs a real (local, reversible) commit with an `executor_success` receipt, while `dry_run` still produces zero side effects. Wired into the `dipeen worker` CLI (local + `--remote`).
- **Strangler cutover invariants (tests)** — locked the single canonical execution path: chat messages never enqueue commands or execute providers; `pm_loop` is proposal-only by default (`DIPEEN_PM_PROPOSAL_ONLY=1`); approval alone (and a dry-run receipt) never marks a task `DONE` — completion requires evidence through the Reconciler.

### Changed
- **README** — explicit D-001 maturity box, Product Alpha status, and a **tunnel safety** note (public `*.trycloudflare.com` tunnels are explicit-test-window only).
- **ALPHA_RUNBOOK** — remote test-window teardown checklist (stop cloudflared, revoke invites, rotate non-default secret).
- **`/api/agents`** — marked **deprecated** (non-breaking `Deprecation`/`Warning`/`Link` headers pointing to `/api/control-plane/*` + the worker HTTP protocol). The legacy poll/report path still works for comparison.

### Safety
- Permission executor default remains `dry_run`; `local_execute` requires explicit `DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute`. Core executes no provider CLI or privileged side effects. 183 API tests green.

## [0.2.1] - 2026-06-03

### Added
- **HTTP permission control loop (dry_run-safe)** — approve → `permission.execute` command → remote worker pulls → `would_execute` receipt → Core persists + reconciles. The Core records decisions only; **no external side effects by default** (`DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run`). `api/app/nat/worker_http.py`, `api/app/services/control_plane.py`, `api/app/routers/control_plane.py`.
- **ALPHA_RUNBOOK.md** — single-machine clone → run → verify, with the safety model spelled out.

### Changed
- One-click runnability: `docker-compose.yml` dev defaults (`DIPEEN_SECRET_KEY`, `DIPEEN_CORS_ORIGINS`, `DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run`); README Quick Start clone URL + Alpha banner + production `POSTGRES_PASSWORD`.

### Internal
- `executors.compute_permission_receipt` shared by local `WorkerNode` and remote `WorkerHttpClient` — one receipt semantics for local and over-the-wire workers.

## [0.2.0] - 2026-06-02

### Added
- **Hermes WSS spine** — distributed control layer (`/ws/hermes/{agent,ui}`): node presence + real-time `LOG_STREAM` relay to the UI.
- **Credit-free subscription execution** — PM-loop calls the Anthropic Messages API directly via the local Claude subscription OAuth token (no API key, $0 credits); `api/app/subscription_llm.py`.
- **`AGENT_EXECUTOR=omo` seam** — run tasks via oh-my-opencode (Ralph Loop) instead of `claude -p`.
- **ProjectGraph** (`/graph`) — team network graph view consuming `/api/graph/nodes`; glass nodes + live presence.
- **CI import-gate** — every `api` + `agent-client` module must import on push (catches trunk-breaking IndentationError/NameError).
- LICENSE (MIT), SECURITY.md (BYOK invariant), `agent-client/.env.example`.
- `dipeen-agent` console command (`[project.scripts]`); agent-client is now pip-installable (fixed hatchling package config).

### Changed
- UI shows **live data only** — removed all `DEMO_*` mock fallbacks across 7 components.
- LoginGate auto-logs-in on localhost (dev-token), removing the local-dev wall.
- Production CORS pinned to `DOMAIN`; deploy gated on pytest.

### Fixed
- agent-client boot: removed orphaned dead block + missing `websockets`/`datetime` imports in `client.py`.
- API boot: missing `hermes` router import in `main.py`.

### Docs
- Frontier research (`docs/research/frontier-agentic-2026.md`), completion audit, layer-cake roadmap, append-only `docs/worklog.md`.

## [0.1.0] - 2026-04-06

### Added
- FastAPI backend with agents/tasks/chat/events routers
- Next.js 14 web frontend with dark theme
- Virtual office canvas (Phaser 3) with LPC sprite characters
- PM-Loop: 5-state machine (IDLE→DISCUSSING→PLANNING→EXECUTING→REVIEWING)
- agent-client: BYOK execution via Claude Code subprocess
- JWT authentication with dev-token for local development
- Docker Compose for full-stack deployment
- Right-click movement + flowing path indicator in office
- AgentCardPanel: bottom slide-up agent card with quick actions
- Proximity bubbles: visual indicator when agents are near each other
- Intent classification (work/question/casual/confirm) + @pm trigger + /task command
- SPEAK/PASS agent review protocol before task execution
- Category model routing (quick→haiku, normal→sonnet) + LLM fallback chain
- Kanban board (Pending / In Progress / Done / Error + Retry)
- Usage dashboard (per-agent token bar chart + estimated cost)
- Profile settings (username/avatar, agent skills/persona/model editing)
- SDK agent loop for non-Anthropic LLMs via OpenAI-compatible interface
- Preemptive compaction at 78% token threshold with WORKSPACE.md re-injection
- demo_check.py: 10-point preflight verification script
- Alembic auto-migration via dedicated migrate service
