# Getting Started

Dipeen OS is the open-source Agentic Slack and control plane for distributed AI
agent teams.

This guide is for a local alpha run. It keeps permissions in `dry_run` mode and
does not require real provider credentials unless you start a real PM loop or
worker.

## 1. Requirements

- Docker and Docker Compose
- Git
- Python 3.11+ for agent clients
- Node.js 18+ for local Web development
- Optional: Cloudflare `cloudflared` for NAT-friendly remote team access
- Optional: provider credentials or local subscriptions for real worker runs

## 2. Start The Local Control Tower

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

The compose file defaults to:

```text
DIPEEN_DEBUG=true
DIPEEN_PERMISSION_EXECUTOR_MODE=dry_run
```

## 3. Verify API State

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/control-plane/summary
curl http://localhost:8000/api/runs
curl "http://localhost:8000/api/events?tail=50"
curl http://localhost:8000/api/permissions?status=requested
curl http://localhost:8000/api/memory-candidates?status=pending
```

Large payloads are fetched by REST. WebSocket events are used for invalidation
and real-time updates.

## 4. Start Local Development

Use this when editing the repo directly instead of Docker.

```bash
cd api
uvicorn app.main:app --reload --port 8000
```

```bash
cd web
npm run dev
```

```bash
cd agent-client
python -m pip install -e .
dipeen-agent doctor
dipeen-agent start
```

Optional PM loop:

```bash
cd api
python pm_loop.py
```

## 5. Add A Worker Machine

On each worker machine:

```bash
python -m pip install -e agent-client
dipeen-agent doctor
dipeen-agent bootstrap --dry-run --role FE --workspace "D:/work/your-project" --network cloudflare
dipeen-agent connect --code <CODE> --api-url <PUBLIC_HTTPS_URL>
dipeen-agent start
```

`bootstrap --dry-run` prints the required packages, Cloudflare status, runner
install commands, and BYOK auth commands without writing provider secrets.

## 6. Cloudflare NAT Model

Dipeen does not require inbound port forwarding on worker machines.

HQ can expose API and WSS through Cloudflare:

```bash
cd api
python -m app.services.public_tunnel
```

Workers connect outbound:

```bash
dipeen-agent connect --code <CODE> --api-url <PUBLIC_HTTPS_URL>
dipeen-agent start
```

Legacy VPS routing can still be used:

```bash
dipeen-agent bootstrap --network vps --legacy-vps-url https://your-vps.example.com
```

## 7. Provider Credentials

Dipeen Core is not a provider runtime and does not need worker provider keys.

- Human and worker provider credentials stay on the worker machine.
- HQ receives status, events, artifacts, permission requests, and state claims.
- `ANTHROPIC_API_KEY` is optional for control-plane-only startup.
- Real PM-loop/provider execution requires a real key or an authenticated local provider CLI.

## 8. Troubleshooting

API unreachable:

```bash
curl http://localhost:8000/health
```

Worker cannot join:

```bash
dipeen-agent status
dipeen-agent doctor
```

Web UI shows stale data:

```bash
curl http://localhost:8000/api/control-plane/summary
```

Permission side effect did not execute:

Check `DIPEEN_PERMISSION_EXECUTOR_MODE`. The default is `dry_run`, so approval
creates a receipt artifact instead of performing the action.
