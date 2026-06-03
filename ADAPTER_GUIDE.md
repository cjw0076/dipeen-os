# Adapter Guide

Provider adapters normalize external runtimes into Dipeen resources.

An adapter should never become the source of truth. It starts runs, streams
events, collects artifacts, and reports state claims. Dipeen verifies and
reconciles.

## Adapter Responsibilities

- report capabilities
- start a run
- stream events
- collect artifacts
- stop a run
- report health
- avoid leaking provider secrets

## Conceptual Interface

```python
class DipeenProviderAdapter:
    def capabilities(self) -> list[str]:
        ...

    async def start_run(self, invocation):
        ...

    async def collect_events(self):
        ...

    async def collect_artifacts(self):
        ...

    async def stop(self):
        ...
```

## Normalized Outputs

Adapters should emit:

- `Event`
- `Artifact`
- `StateClaim`
- `PermissionRequest`
- `MemoryCandidate`

## Rules

- Do not execute privileged side effects directly through Core.
- Do not send provider keys to HQ.
- Use `dry_run` receipts for permission execution by default.
- Include enough metadata for artifact lineage.
- Prefer deterministic checks over provider self-report when possible.

## Candidate Packages

- `dipeen-provider-claude`
- `dipeen-provider-codex`
- `dipeen-provider-omo`
- `dipeen-provider-hermes`
- `dipeen-provider-gemini`
- `dipeen-provider-opencode`
- `dipeen-provider-local`
