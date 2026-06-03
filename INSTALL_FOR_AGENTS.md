# Install Dipeen For This Repository

This file is written for Claude, Codex, and other high-quality development
agents that are asked to install or verify Dipeen OS.

You are the developer operating on this repository. You are not Dipeen, OMO, or
Hermes. Do not pretend to be a runtime component. Your job is to set up and
verify the project.

## Position

Dipeen is not a provider clone.

```text
Provider CLI
  -> harness wrapping such as OMO or Hermes
  -> Dipeen team-base wrapping
```

Dipeen is the organization control plane. Providers execute. Harnesses improve
execution or memory. Dipeen governs commands, events, artifacts, permissions,
memory candidates, and reconciled state.

## Agent Prompt

Use this prompt when handing setup to another development agent:

```text
Install Dipeen OS for this repository.
Read README.md, INSTALL_FOR_AGENTS.md, docs/GETTING_STARTED.md,
docs/ARCHITECTURE.md, and docs/SECURITY_MODEL.md.
Keep permission mode in dry_run.
Do not collect or transmit provider secrets.
Verify docker compose config and the Web/API startup path.
Record any failed command with the exact error and next fix.
```

## Current Alpha Commands

Local control tower:

```bash
cp .env.example .env
docker compose up --build
```

Agent client:

```bash
python -m pip install -e agent-client
dipeen-agent doctor
dipeen-agent bootstrap --dry-run --role FE --workspace "D:/work/your-project" --network cloudflare
dipeen-agent connect --code <CODE> --api-url <PUBLIC_HTTPS_URL>
dipeen-agent start
```

NAT worker mode:

```bash
dipeen-agent worker --once
dipeen-agent worker --capabilities provider.claude,workspace.write,git.diff
```

Cloudflare tunnel helper:

```bash
cd api
python -m app.services.public_tunnel
```

## Target HQ CLI

These commands describe the product target and may not be implemented yet:

```bash
dipeen doctor
dipeen bootstrap --dry-run
dipeen bootstrap --apply
dipeen demo run
dipeen web open
dipeen worker start --local
dipeen worker --remote <url>
```

Do not document target commands as working unless the repo implements them.

## Safety Rules

- Keep `DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run` for public alpha verification.
- Do not read, print, or upload provider keys.
- Do not run destructive git commands.
- Do not push, deploy, or create PRs unless the human explicitly asks.
- Treat provider output as a claim until Dipeen verifies and reconciles it.

## Verification Checklist

```bash
docker compose config
```

```bash
cd api
python -m pip install -e ".[dev]"
pytest -q
```

```bash
cd web
npm run build
```

When full startup is requested:

```bash
docker compose up --build
curl http://localhost:8000/health
curl http://localhost:8000/api/control-plane/summary
```

Browser smoke:

- `/` and `/app`: Control Tower
- `/dashboard`: Run Workbench
- `/meeting/ER-1247`: meeting and brief surface
- `/onboarding`: launcher/BYOK setup
- `/office`: visual overlay over canonical state
- `/graph`: graph overlay over canonical state
