# Dipeen OS — Alpha Preview Runbook

Single-machine, local-first agentic control tower. **No external side effects are executed by default** —
privileged actions run in `dry_run` mode and produce "would-execute" receipts only.

## 0. See it instantly (no Docker, no API key)

```bash
cd api && pip install -e . && dipeen demo
```

A keyless, deterministic walkthrough of the canonical path with **real** evidence: false-done caught →
retry earns a real `code_patch` → risky PR gated to a dry-run receipt → decision → memory candidate.

## 1. Run

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os
cp .env.example .env
# edit .env:
#   DIPEEN_DEBUG=true
#   DIPEEN_SECRET_KEY=dev-secret
#   ANTHROPIC_API_KEY=sk-ant-...      # optional (only needed for real Claude workers)
docker compose up --build
```

## 2. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/control-plane/summary
# Web UI:
open http://localhost:3000
```

## 3. Run the test suite

```bash
cd api
python -m pip install -e ".[dev]"
pytest -q
```

## 4. Safety model (read this)

- **Default permission executor mode: `dry_run`.** No real PR / push / deploy is performed.
- Approving a privileged action enqueues a `permission.execute` command; a worker produces a
  `would_execute` receipt artifact — **the Core never executes side effects**.
- To opt in to real execution: `DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute` (allowlisted actions only:
  git.commit / git.push / github.pr.create / github.issue.create).

## 4b. Remote test window (Cloudflare tunnel) — teardown checklist

A `*.trycloudflare.com` tunnel exposes your local HQ publicly. Product Alpha auth is not
production-grade, so treat the tunnel as an **explicit, time-boxed test window**.

```bash
# open (test window only)
cd api && python -m app.services.public_tunnel    # prints public HTTPS URL + join command

# teardown (when the window closes)
# 1. Ctrl+C the tunnel helper (stops cloudflared)
# 2. revoke invite codes minted during the session
# 3. rotate DIPEEN_SECRET_KEY if it was anything other than a throwaway dev value
# 4. stop the local API/Web if you are done
```

Never leave a public tunnel running unattended.

## 5. What works in this alpha

- API + Web UI control tower (`/api/control-plane/summary`, runs / events / artifacts / permissions / memory)
- task → run.start command → worker pull/lease → provider execution → artifact / state-claim → verify / reconcile
- permission inbox: approve / reject → `permission.execute` command → worker `dry_run` receipt
- Claude / Codex as simple per-PC workers (local `dipeen worker`, or remote `dipeen worker --remote <url>`)

## 6. Experimental / not yet stable

- Real GitHub PR creation (opt-in `local_execute` only)
- OMO (composite team) / Hermes (memory/skill) integrations
- Multi-PC team invite + onboarding
- Automated production deploy

## 7. Layout

| dir | what |
|---|---|
| `api/app/nat/` | NAT layer: contracts, adapters, outbound/inbound, verifier/reconciler, permission, worker, executors |
| `api/app/routers/control_plane.py` | control-plane HTTP API surface |
| `api/app/services/control_plane.py` | control-plane service (NAT-backed) |
| `web/` | Next.js control tower UI |
| `agent-client/` | per-PC agent client |
