# Bootstrap

This is the public alpha bootstrap contract.

## Human Bootstrap

```bash
git clone https://github.com/cjw0076/dipeen-os.git
cd dipeen-os
cp .env.example .env
docker compose up --build
```

Open http://localhost:3000.

## Worker Bootstrap

```bash
python -m pip install -e agent-client
dipeen-agent doctor
dipeen-agent bootstrap --dry-run --role FE --workspace "D:/work/your-project" --network cloudflare
```

The bootstrap command checks:

- git
- python
- node
- uv
- cloudflared
- runner install commands
- runner auth commands
- BYOK boundary
- next `connect` and `start` commands

## HQ Tunnel

```bash
cd api
python -m app.services.public_tunnel
```

Workers connect outbound:

```bash
dipeen-agent connect --code <CODE> --api-url <PUBLIC_HTTPS_URL>
dipeen-agent start
```

## Bootstrap Principles

- Dipeen Core owns team state.
- Worker machines own provider credentials.
- Provider output becomes Dipeen evidence.
- Dangerous side effects become permission requests.
- Public alpha verification stays in `dry_run`.
