# Verifier Guide

Verifiers turn provider output into evidence.

Dipeen should not mark work as done only because a provider said it is done.
Artifacts and checks must support the final state.

## Verifier Types

- pytest
- Playwright
- TypeScript build
- npm test
- ruff
- secret scan
- policy check
- PR metadata check
- artifact lineage check

## Verifier Output

A verifier should produce:

- check name
- status
- command or method
- started and finished timestamps
- stdout/stderr summary
- artifact references
- failure reason

## Rules

- Prefer deterministic checks.
- Keep outputs small enough for UI summaries.
- Store large logs as artifacts.
- Never hide failed checks.
- Never mutate workspace state unless explicitly configured.

## Registry Direction

Target commands:

```bash
dipeen verifier install secret-scan
dipeen verifier install playwright
dipeen verifier install pytest
dipeen verifier install typescript
```

These are roadmap commands until the HQ CLI exists.
