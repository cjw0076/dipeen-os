# Roadmap

Dipeen OS is aiming to become the default open control plane for distributed AI
agent teams.

## North Star

```text
Claude, Codex, OMO, Hermes, and local workers can run anywhere.
Dipeen lets them operate as one organization.
```

## Phase 0 - Public Alpha Surface

Goal: a new contributor can clone, run, understand, and trust the project.

- README public alpha rewrite
- Docker compose local startup verified
- Control Tower visible at http://localhost:3000
- `/api/control-plane/summary` returns live state
- Permission dry-run demo
- Artifact viewer
- Memory candidate queue
- Alpha runbook
- Architecture, security, getting-started, and agent-install docs
- v0.1.0-alpha release package and demo video

## Phase 1 - One-Command Demo

Goal: run a full story without provider credentials.

Acceptance:

```text
git clone
docker compose up --build
open localhost
run demo team
see goal -> meeting -> run -> artifact -> permission -> memory -> summary
```

Demo worker should generate:

- agent room messages
- tasks
- runs
- events
- artifacts
- permission request
- dry-run receipt
- memory candidate
- final reconciled summary

## Phase 2 - Agent-Installable Product

Goal: Claude/Codex-style development agents can install Dipeen for a repository.

Current node-side CLI:

- `dipeen-agent doctor`
- `dipeen-agent bootstrap`
- `dipeen-agent setup`
- `dipeen-agent connect`
- `dipeen-agent start`
- `dipeen-agent worker`

Target HQ CLI:

- `dipeen doctor`
- `dipeen bootstrap --dry-run`
- `dipeen bootstrap --apply`
- `dipeen demo run`
- `dipeen web open`
- `dipeen worker start --local`
- `dipeen worker --remote <url>`

## Phase 3 - OMO And Hermes As Instruments

OMO integration:

```text
Dipeen task -> OMO team run -> OMO messages -> Dipeen room events
-> Dipeen artifacts -> Dipeen permissions
```

Hermes integration:

```text
Dipeen artifacts -> Hermes memory/skill proposal
-> Dipeen memory candidate queue -> human promote -> organization memory
```

Principle:

```text
OMO builds.
Hermes remembers.
Dipeen governs.
```

## Phase 4 - Team Blueprint Marketplace

Goal: contributors share team operating systems, not just agent plugins.

Examples:

- `startup`
- `solo-founder`
- `security-audit`
- `refactor-squad`
- `research-lab`
- `release-manager`

Blueprints should define roles, providers, policies, workflows, verifiers, and
permission requirements.

## Phase 5 - Evidence Graph And Organization Memory

Goal: Dipeen can answer:

- Why did the team choose this approach?
- Who approved it?
- Which agent implemented it?
- What evidence passed?
- Which PR shipped it?
- Was that decision reused later?

Evidence graph:

```text
Goal -> Task -> Run -> Agent -> Artifact -> Verification
-> Permission -> Decision -> Memory -> Future Task
```

## Ecosystem Tracks

- Provider Adapter SDK
- Team Blueprint SDK
- Verifier Registry
- Worker packaging
- Demo scenarios
- Public docs site
- Release cadence
