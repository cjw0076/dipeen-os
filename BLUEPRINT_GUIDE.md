# Blueprint Guide

A Dipeen team blueprint defines how an agent team operates.

Blueprints are not just provider lists. They describe roles, policies, workflows,
verifiers, permissions, and memory rules.

## Example

```yaml
name: startup
roles:
  pm:
    provider: dipeen-conductor
  implementation:
    provider: omo
  frontend:
    provider: claude
  backend:
    provider: codex
  memory:
    provider: hermes
  qa:
    provider: gemini
policies:
  git.push: requires_approval
  github.pr.create: dry_run_by_default
  deploy.production: denied
workflows:
  feature:
    - discuss
    - implement
    - verify
    - approve
    - remember
```

## Blueprint Fields

- `name`
- `roles`
- `providers`
- `policies`
- `workflows`
- `verifiers`
- `permissions`
- `memory`

## Marketplace Direction

The extension surface is team operating systems:

- `startup`
- `solo-founder`
- `security-audit`
- `refactor-squad`
- `research-lab`
- `release-manager`

People should share how teams work, not only which agent to run.
