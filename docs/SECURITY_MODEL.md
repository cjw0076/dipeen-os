# Security Model

Dipeen is built around one rule:

Provider output is never trusted until Dipeen verifies, reconciles, and records
evidence.

## Trust Boundaries

### Dipeen Core

Core stores:

- commands
- events
- artifacts
- permission requests
- memory candidates
- reconciled state

Core does not need member provider credentials.

### Worker Machine

The worker machine owns:

- local provider credentials
- local subscriptions
- workspace files
- local shell execution
- provider CLI sessions

Workers send normalized evidence to Dipeen.

### Provider Runtime

Providers can produce useful output, but Dipeen treats it as a claim:

- an event is not final state
- an artifact is not automatically verified
- a run result is not automatically done
- a PR request is not automatically executed
- a memory proposal is not automatically promoted

## BYOK

Bring your own key means provider credentials stay local.

Dipeen HQ must not receive, store, or proxy member provider keys. The launcher
prints auth commands, but it does not collect secrets.

## Permission Ledger

Risky actions become permission requests:

- git push
- GitHub PR create
- deploy
- production mutation
- secret access
- external account action

Default behavior:

```text
approve -> permission.execute command -> worker dry_run receipt -> artifact
```

Real execution requires:

```text
DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute
```

Only allowlisted actions should run in `local_execute`.

## Dry-Run Receipts

Dry-run receipts are first-class artifacts. They should show:

- requested action
- actor
- target
- command payload summary
- why it was requested
- what would have happened
- whether execution was skipped

## Secret Handling

Never commit:

- `.env`
- API keys
- OAuth credentials
- provider session files
- tunnel tokens
- private keys

If a key leaks, rotate it immediately.

## Network Model

Remote workers should connect outbound to HQ through HTTPS/WSS. Cloudflare tunnel
is the preferred alpha path for NAT traversal. Legacy VPS routing is supported
when the team already trusts that deployment.

## Production Checklist

- Replace `DIPEEN_SECRET_KEY`
- Restrict `DIPEEN_CORS_ORIGINS`
- Keep permission mode in `dry_run` until policies are tested
- Use HTTPS/WSS
- Separate dev and production databases
- Review worker workspace permissions
- Keep provider credentials on worker machines
- Enable audit/event retention
