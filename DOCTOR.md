# Doctor

Doctor commands inspect the local environment and print actionable setup status.

## Current Node Doctor

```bash
python -m pip install -e agent-client
dipeen-agent doctor
```

It checks:

- core tools: git, python, node, uv, cloudflared
- available runner adapters
- install commands for missing runners
- auth commands for BYOK provider setup
- HQ URL from environment

Exit code:

- `0`: core requirements and at least one runner are available
- `1`: missing core requirement or no runner is available

## Current Related Commands

```bash
dipeen-agent setup --dry-run
dipeen-agent bootstrap --dry-run --role FE --workspace "D:/work/your-project"
dipeen-agent runner list
dipeen-agent status
```

## Target HQ Doctor

The HQ `dipeen doctor` command is a roadmap item. It should eventually verify:

- compose config
- API health
- Web build
- NAT queue
- permission executor mode
- database migration status
- WebSocket connectivity
- demo data availability
- provider adapter registration

Until then, use:

```bash
docker compose config
curl http://localhost:8000/health
curl http://localhost:8000/api/control-plane/summary
```
