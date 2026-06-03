# Support Levels — Dipeen runner support taxonomy

> **Dipeen은 "설치됨"을 "지원됨"이라 주장하지 않는다. 증거(evidence)가 나온 뒤에만 주장한다.**
> Install detected ≠ support claim. `probe healthy`만 `advertised`가 될 수 있다 (Evidence First).

OMO/Hermes처럼 빠르게 변하는 upstream CLI를 control plane에 붙일 때, "설치됨 = 지원됨"으로 묶으면
첫 실패 한 번에 신뢰가 무너진다. 그래서 support는 **단계로 분리**하고, 각 단계는 코드로 강제한다.

## 5 levels

| level | 의미 | 코드 출처 (SSOT) |
|---|---|---|
| `installed` | binary/config/plugin 흔적 있음 | `ProviderInspection.installed` (static which/파일) |
| `inspectable` | static capability surface 확인됨 | `ProviderInspection.capabilities` |
| `probe_healthy` | harmless live probe 통과 | `dipeen providers probe <name>` (M11b, worker 경유) |
| `advertised` | probe_healthy **그리고** policy상 노출 허용 | `ProviderInspection.capability_advertised` — **probe healthy일 때만 True** (static inspect는 항상 False) |
| `supported` | CI/e2e/doctor/docs까지 green | 이 문서 + CI gate (메타 — 코드 단일 필드 아님) |

**불변식**: `installed`라도 `advertised=False`가 기본. live probe가 healthy를 증명해야 광고된다.
task routing은 `advertised` runner만 기본 후보로 쓴다. preview runner는 명시 선택 + warning.

## 현재 support matrix (Public Alpha, 2026-06-03)

| runner | level | 근거 |
|---|---|---|
| `claude-code` | **supported** | 실측 headless e2e green (M5) |
| `codex` | **supported** | 실측 headless e2e green (M5) |
| `omo-opencode` | **preview** | M11 NAT 계약(outbound/adapter/inbound) ✓ · live probe/CI 미고정 · bun runtime 의존(ENOENT) |
| `omo-codex-light` | **preview** | 동상(codex 기반) |
| `hermes` | **preview** | NAT 계약 ✓ · credential/model(`hermes model`) probe 미고정 |

## Not yet (claim 금지)

- production public tunnel — Cloudflare는 test-window only (ALPHA_RUNBOOK)
- unattended multi-org hosting
- stable OMO/Hermes first-class execution

## 정책

- **support claim discipline**: probe_healthy 전엔 advertised 금지. UI badge/README/doctor가 level을 정확히 표시.
- **memory boundary**: Hermes local memory = worker-local. Dipeen org memory = `memory_candidate` → 사람 promote/reject (자동승격 금지).
- **permission**: 모든 privileged action은 permission ledger 경유. 기본 `dry_run` (`DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute`로만 opt-in).
- **BYOK**: provider credential은 worker 로컬. Core(HQ)는 provider key를 받지 않는다.

## 외부/내부 포지셔닝

```
External: Dipeen is a team control plane for local AI agent workers.
          It does not replace OMO, Hermes, Claude Code, or Codex. It coordinates them.
Internal: OMO builds. Hermes reasons/remembers. Dipeen governs.
Claim:    Dipeen does not claim a runner is usable because it is installed.
          Dipeen claims it only after it produces evidence.
```
