# Dipeen — Production Pitch & Architecture Figure Set

> **Agents do the work. Dipeen makes the work accountable.**
> Agent는 일을 한다. Dipeen은 그 일이 믿을 수 있게 만든다.

This is the production-pitch / demo-level alignment of Dipeen: one product definition, one architecture
figure set, one network story, one demo flow, one deck outline. It does not replace the prose docs —
it is the deck-ready spine. Source of truth for terms: [`ARCHITECTURE.md`](ARCHITECTURE.md),
[`SUPPORT_LEVELS.md`](SUPPORT_LEVELS.md), [`SECURITY_MODEL.md`](SECURITY_MODEL.md).

---

## 1. Product Definition & Positioning

### 1.1 One line (memorize this)
**Dipeen is an evidence-first control plane for human + AI agent teams.**
한국어: **Dipeen은 인간과 AI agent 팀을 위한 Evidence-First Control Plane이다.**

### 1.2 Deck-ready definition
```text
Dipeen is an evidence-first control plane for human + AI agent teams.

It lets distributed workers run Claude, Codex, OMO, Hermes, and local tools from their own machines,
while Dipeen coordinates tasks, gates permissions, collects artifacts, verifies claims,
reconciles canonical team state, and promotes validated knowledge into team memory.
```

한국어:

```text
Dipeen은 인간과 AI agent 팀을 위한 Evidence-First Control Plane이다.

각 worker는 자기 로컬에서 Claude, Codex, OMO, Hermes, local tools를 실행하고,
Dipeen은 작업 분배, 권한 승인, artifact 수집, claim 검증, canonical state 정리,
그리고 검증된 지식의 팀 memory 승격을 담당한다.
```

### 1.3 What it is / is not
| Dipeen **is** | Dipeen **is not** |
|---|---|
| The team operating system for AI agent workers | An LLM / a model |
| Rooms · tasks · runs · artifacts · permissions · memory for agents | A Claude/Codex/Cursor replacement |
| Provider-neutral governance + evidence + reconciliation | An OMO/Hermes replacement |
| The layer **above** the agents | A task board / a Slack clone |

### 1.4 The thesis
```
Agents can now do the work.
But teams cannot yet manage the work.
```
The problem is not a shortage of agents. The problem is: *who owns what, which agent ran, what changed,
is it really done, who approved the risky action, which decision becomes team memory, who retries on failure?*
There is no team-scale layer that unifies this. **Dipeen is that layer.**

### 1.5 Role clarity (the layer cake)
```
Claude / Codex / OMO / Hermes / Gemini / local tools   ← the hands (work + remember)
                  ↓  Worker / Adapter                   ← local execution node (BYOK)
            Dipeen NAT + Core                            ← normalize · verify · gate · reconcile
        Web Control Tower / Team Space                  ← what humans see
```
| Provider | Role in Dipeen |
|---|---|
| **Claude / Codex** | the work — reasoning, code edit, execution, review |
| **OMO** (oh-my-openagent) | amplifies execution — multi-agent coding harness (runner candidate) |
| **Hermes** | remembers & reasons — memory / skills / long cognition (runner candidate) |
| **Dipeen** | **coordinates, verifies, gates, reconciles, governs memory** |

> **OMO builds. Hermes remembers. Dipeen governs.** Dipeen does not compete with them — it **wraps** them as workers.

### 1.6 Audience language
| Audience | Say it this way |
|---|---|
| Investor / CEO | **Dipeen is the operating system for AI agent teams.** AI agents are becoming workers; Dipeen gives them rooms, tasks, permissions, evidence, and memory. |
| CTO / developer | **Dipeen is a provider-neutral control plane.** It normalizes agent output into canonical tasks, events, artifacts, permission requests, state claims, and memory candidates. |
| End user | 여러 AI agent를 한 팀방에 넣고, 누가 뭘 했는지, 진짜 끝났는지, 위험한 작업은 승인됐는지, 어떤 결정이 기억돼야 하는지 볼 수 있게 해주는 제품. |
| One-sentence pitch | **Dipeen turns scattered AI agents into an accountable team.** |

### 1.7 Alignment table (kill the ambiguity)
| Question | Aligned answer |
|---|---|
| Is Dipeen an agent? | No. A control plane that operates agents. |
| Is Dipeen Slack? | It has room UX, but the core is evidence / permission / state. |
| Is Dipeen orchestration? | It includes orchestration, but it is **governance** — a control plane. |
| Does Dipeen compete with OMO/Hermes? | No. It hosts them as workers / runtimes. |
| Core differentiator? | **evidence-first · permission-gated · provider-neutral · team-memory governance.** |
| First killer demo? | catch an agent's **false-done → NEEDS_RETRY**, then earn **DONE** by evidence. |

### 1.8 Common misreadings to block early
| Misreading | Correct framing |
|---|---|
| The Dipeen host must have the agents installed. | No. The host is HQ/control plane. Claude/Codex/OMO/Hermes run on worker machines. |
| The Web UI alone makes agents work. | No. The Web UI is a control surface. A joined worker is required for the execution loop. |
| If an agent says `done`, the task is done. | No. `StateClaim` is the agent's assertion; canonical `TaskState` is reconciled from evidence. |
| Memory is auto-saved. | No. Agents propose memory; Dipeen stores a `memory_candidate`; humans promote or reject it. |
| Installed provider means supported provider. | No. A provider is routable only after a healthy probe and policy advertisement; see §6. |

---

## 2. Architecture Figure Set (warm-beige academic; 8 sequential figures)

**Style note for the figure renderer:** warm beige background (`#F3ECE0`), ink `#3A342B`, accent terracotta
`#B5654A` for the trust/evidence path, muted sage `#6E7B5B` for workers. Rounded rectangles, thin 1.5px strokes,
one idea per figure, captions below. Build the figures up in sequence (Fig 1 → Fig 8) so a presenter can layer them.

### Fig 1 — Dipeen Control Plane HQ (the room)
- Center: a single rounded panel **"Dipeen HQ (Control Plane)"**.
- Inside, three stacked bands: **Web Control Tower** (top), **Core API** (middle), **Ledgers & Evidence Store** (bottom).
- Left margin: three human silhouettes (PM · FE · QA) entering an arrow into HQ.
- Caption: *"One room. Humans and agents share goals, tasks, runs, artifacts, permissions, decisions, memory."*

### Fig 2 — Core Services (the canonical brain)
- HQ expanded into labeled service boxes: **Rooms/Messages · Task & Run Orchestration · Command Queue ·
  Worker Registry · Verifier · Reconciler · Permission Ledger · Memory-Candidate Queue · Event/Artifact Ingest**.
- The Conductor box marked **"deterministic FSM (no LLM)"** in terracotta.
- Caption: *"The Core decides and records. It never executes a provider CLI."*

### Fig 3 — Data Layer (event-sourced ledger)
- Bottom band of HQ: cylinders/files — **Event log (append-only) · Artifact store · Run store · State ledger ·
  Permission ledger · Memory-candidate JSONL**.
- A small replay arrow: *"current state = replay(events)"*.
- Caption: *"Append-only evidence. State is derived, not asserted."*

### Fig 4 — Distributed Worker Nodes (the hands, elsewhere)
- Three sage machine icons OUTSIDE HQ: **민준 laptop · CI runner · cloud VM**.
- Each holds its own small lock (🔒 local credential) and a local CLI chip (claude / codex / omo / hermes).
- Dashed **pull** arrows from workers → HQ command queue (workers initiate, HQ never pushes).
- Caption: *"Workers run providers locally with their own keys (BYOK). They pull work; HQ never holds a key."*

### Fig 5 — Provider / Integration Layer (NAT)
- A translation membrane between worker output and Core: **raw provider output → Event · Artifact ·
  StateClaim · PermissionRequest · MemoryCandidate · SkillCandidate**.
- Label the membrane **"NAT — Normalized Agent Translation"**; note *"Core knows only canonical types,
  never claude/codex/omo/hermes internals."*
- Caption: *"Heterogeneous agents in. One canonical vocabulary out."*

### Fig 6 — Security & Trust Layer (the gate)
- Two gates in terracotta on the worker→Core path: **Permission Gate** (privileged actions) and
  **Verifier/Reconciler** (claims → evidence).
- A "dry-run receipt" stamp; a key icon with a red ⃠ over HQ (*HQ holds no provider key*).
- Caption: *"Default dry-run. Risky actions need approval. 'done' is earned by evidence, not declared."*

### Fig 7 — Network Infrastructure (HQ ⇄ worker over NAT) — see §3 for the detailed figure.

### Fig 8 — The Dipeen Loop
- A circle of 8 nodes: **Idea → Task → Assign/Lease → Run → Evidence → Verify → Decide → Memory → (back to Idea)**.
- The Verify node forks: ✓ verified_done / ⟳ needs_retry / ⛔ blocked / 🔒 awaiting_permission.
- Caption: *"The accountable cycle. Every loop produces evidence and, sometimes, team memory."*

---

## 3. Network Infrastructure Figure (detailed)

**Style:** same palette. Two zones split by a vertical dashed "NAT boundary".

```
        ┌──────────── Dipeen HQ (one host) ────────────┐         ┌────── Worker Nodes (anywhere) ──────┐
        │  Web / Control Tower                          │         │  민준 laptop   claude CLI  🔒 local  │
        │  Core API  (FastAPI)                           │ ◀─pull─ │  수민 laptop   codex  CLI  🔒 local  │
        │  Command Queue · Worker Registry               │ ─lease▶ │  CI runner     omo* / hermes* (probe)│
        │  State Ledger · Permission Ledger · Evidence   │ ◀─result│  ...  pull command · run local CLI   │
        │  ✗ no provider key                             │  events │       · upload artifact/event/claim  │
        └────────────────────────────────────────────────┘         └──────────────────────────────────────┘
                         ▲ outbound-only HTTPS/WSS (Cloudflare tunnel; test-window only)
```
- **HQ owns:** API · Web/Control Tower · State Ledger · Permission Ledger · Evidence Store. No keys, no execution.
- **Worker owns:** local CLIs + credentials, repo workspace, execution. Pulls commands, returns
  artifact / event / state-claim / permission-request.
- **Direction:** workers + HQ initiate **outbound** connections (no router port-forwarding). Remote teammates
  join over a Cloudflare tunnel — **explicit test-window only**, revocable, audited (`ALPHA_RUNBOOK`).
- **Liveness:** local agents send `/api/agents/{id}/heartbeat` with `idle/working/offline`; NAT workers send
  `/api/workers/{id}/heartbeat`. HQ stores `last_heartbeat`, filters stale workers from routing, and the
  Control Tower renders heartbeat age. The browser does not act as the source-of-truth heartbeat.
- **Default mode:** `dry_run`. Privileged actions (git.commit / push / PR / deploy / shell / secret) pass the
  permission gate → dry-run receipt unless `DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute` is explicitly set.
- Caption: *"The key never leaves the worker. The Core never runs an agent. Distance is bridged outbound-only."*

---

## 4. Team Workspace & Demo Flow (Evidence First)

### 4.1 Team-unit experience (who does what)
1. A human drops a **goal** into a Dipeen room.
2. **Coordinator** (propose-only, worker-plane LLM) decomposes it into routed **task candidates** — humans approve.
   *(`core/coordinator.py` — runs on a worker's BYOK provider, never confirms; Core holds no key.)*
3. **Routing** leases each task by capability (`role.*` / `provider.*` / `repo.*`) — only the matching teammate's worker takes it.
4. **Worker** runs the local CLI (Claude/Codex/OMO/Hermes) and uploads evidence.
5. **Verifier/Reconciler** does NOT trust "done" — it checks artifact / diff / test / receipt → **verified_done · needs_retry · blocked**.
6. Decisions/learnings become **memory candidates** — a human promotes/rejects (Org Memory governance).

### 4.2 First demo (DON'T show flashy automation — show accountability)
```
idea → task decomposition → worker assignment → local CLI execution
  → FALSE-DONE detected → needs_retry → real artifact submitted
  → permission request → dry-run receipt → verified_done → memory candidate review
```
> The moment that sells it: an agent says "done", Dipeen **refuses** it for lack of evidence, the agent
> tries again with a real change, and only then is it DONE. *"Oh — this isn't Slack for agents, it's an OS for agents."*

### 4.3 Minimum success criteria

**Deterministic CI proof:** `cd api && python -m app.demo.dogfood_loop --json`

| Criterion | Target | CI summary field |
|---|---:|---|
| workers joined | ≥ 2 | `workers` |
| runners used | claude + codex | `runner_types` |
| tasks leased | ≥ 3 | `leased_tasks` |
| artifacts | ≥ 3 | `artifacts` |
| permission requests | ≥ 1 | `permission_requests` |
| needs_retry | ≥ 1 | `needs_retry` |
| verified_done | ≥ 1 | `verified_done` |
| memory candidates | ≥ 1 | `memory_candidates` |
| dry-run receipts | ≥ 1 | `dry_run_receipts` |
| provider keys at HQ | 0 | `provider_key_leak == false` |

**Manual operator proof:** `python scripts/team_test.py` when real Claude/Codex CLIs and local BYOK auth are ready.
The script prints provider probe results first, runs only in a scratch workspace, keeps `dry_run` as the
executor mode, and treats OMO/Hermes/OpenClaw as preview/probe-only routes outside the success criteria.

---

## 5. Production Pitch Deck — outline (TOC)

1. **Title** — *Agents do the work. Dipeen makes the work accountable.*
2. **The shift** — agents became workers; teams can't yet manage them (the 7 unanswered questions).
3. **Category** — evidence-first control plane for distributed AI agent teams (not orchestration, not Slack).
4. **The layer cake** — Claude/Codex/OMO/Hermes → Worker → NAT+Core → Control Tower (Fig 1).
5. **The Dipeen Loop** — Idea→…→Memory (Fig 8).
6. **Killer demo** — false-done → needs_retry → evidence → DONE (the §4.3 numbers).
7. **Evidence First** — StateClaim ≠ TaskState; verifier/reconciler (Fig 6).
8. **Permissioned action** — default dry-run; permission ledger; dry-run receipts.
9. **BYOK & distributed workers** — key never leaves the worker; HQ runs nothing (Fig 4, §3).
10. **NAT** — heterogeneous agents → one canonical vocabulary (Fig 5).
11. **Org memory governance** — memory candidate → human promote/reject (not auto-saved).
12. **Support discipline** — installed ≠ supported; the 7-level taxonomy (§6).
13. **Status & roadmap** — Public Alpha (Core spine ✓); Public v0 (team invite + OMO/Hermes first-class) next.
14. **Ask / CTA** — `cd api && python -m app.demo.dogfood_loop --json` (keyless), then invite a teammate.

---

## 6. Support-Level Taxonomy (7-level, public-facing)

Matches [`SUPPORT_LEVELS.md`](SUPPORT_LEVELS.md). **Invariant: install detected ≠ support claim. Only
`probe_healthy` may become `advertised`.**

| # | level | meaning | code SSOT |
|---|---|---|---|
| 0 | `not_installed` | binary/config absent | `ProviderInspection.installed == False` |
| 1 | `installed` | binary/config/plugin present | `ProviderInspection.installed` (static which/file) |
| 2 | `inspectable` | static capability surface read | `ProviderInspection.capabilities` |
| 3 | `probe_failed` | live probe ran but unhealthy (e.g. omo `bun ENOENT`) | `providers probe` → `ok=False` (runtime_blocker) |
| 4 | `probe_healthy` | harmless live probe passed | `dipeen providers probe <name>` (worker-run) |
| 5 | `advertised` | probe_healthy **and** policy allows exposure | `ProviderInspection.capability_advertised` (True only after healthy probe) |
| 6 | `supported` | CI / e2e / doctor / docs green | this doc + CI gate (meta) |

**Current matrix (Public Alpha):** `claude-code` **supported** · `codex` **supported** ·
`omo-opencode` / `omo-codex-light` / `hermes` **preview** (NAT contract ✓, live probe/CI not pinned;
omo blocked on the `bun` runtime). Routing uses only `advertised`+ runners by default; preview needs explicit opt-in + warning.

---

## 7. Invariants (the discipline that makes the pitch true)

- **Evidence First** — an agent's "done" is a `StateClaim`, never the canonical `TaskState`. The Reconciler decides DONE only with artifact/check evidence; else NEEDS_RETRY.
- **Permissioned Action** — every privileged action goes through the permission ledger; default `dry_run`; `local_execute` is explicit opt-in.
- **BYOK / Core executes nothing** — provider credentials stay on the worker; HQ holds no key and runs no provider CLI for side effects.
- **Support discipline** — `installed` ≠ `advertised`. `capability_advertised=True` only after a healthy live probe.
- **Org Memory governance** — memory is never auto-saved; agent proposes → `memory_candidate` → human promote/reject.
- **Governance, not replacement** — Dipeen does not replace agents; it makes agents work as an accountable team.

---

*Sources: README · `docs/ARCHITECTURE.md` · `docs/SUPPORT_LEVELS.md` · `docs/SECURITY_MODEL.md` ·
`api/app/demo/dogfood_loop.py` · `scripts/team_test.py` (§4.3). Decisions: Vault
`2026-06-03-dipeen-category-lock`, `...-coordinator-head-agent`, `...-provider-install-print-first`.*
