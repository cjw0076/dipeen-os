"""Provider Lifecycle — print-first opt-in 설치 + probe-health 기반 capability 광고 게이트.

사용자 결정문(2026-06-03):
- Bootstrap은 uv + dipeen-agent + join + *필요한 runtime deps*까지만 자동.
- OMO/Hermes **본체**는 join 중 자동설치하지 않는다 — print-first, --execute는 명시적 opt-in.
- capability(provider.X)는 **probe healthy일 때만** 광고(설치만으론 광고 금지 — Evidence First).

세 축(분리해서 보고):
  runtime deps (bun/node)  : provider 실행에 필요한 *범용* 런타임 — 자동설치 OK(멱등)
  provider 본체 (omo/hermes): 특정 provider 바이너리 — print → 사용자 opt-in
  auth (BYOK)              : provider 인증 — **절대 자동화 안 함**(여기서 다루지 않음)

Lifecycle: MISSING → INSTALL_HINTED → USER_INSTALLED → PROBED → HEALTHY → CAPABILITY_ADVERTISED
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional


# ──────────────── 타입 ────────────────
@dataclass
class RuntimeDep:
    """provider 실행에 필요한 범용 런타임(provider 본체와 분리). available=PATH 기반 best-effort —
    실제 실행 가능성은 live probe가 확정(예: bun.ps1 shim은 PATH에 있어도 omo는 spawnSync로 죽음)."""
    name: str
    available: bool
    install_cmd: str = ""
    purpose: str = ""


@dataclass
class InstallPlan:
    provider: str
    install_hint: str                       # 공식 본체 설치 명령(업스트림 출처 — dipeen이 패키징/재배포 안 함)
    runtime_deps: list[RuntimeDep] = field(default_factory=list)


# ──────────────── catalog (provider 본체 설치 명령 — 업스트림 공식 출처) ────────────────
# 출처: 각 provider의 inspect.py / runners(install_cmd). dipeen은 이 명령을 *보여주거나*(print)
# 명시적 opt-in 시 *대행 실행*만 한다 — 본체를 동봉/미러링/재배포하지 않는다.
_INSTALL_HINT: dict[str, str] = {
    "omo": "bunx oh-my-openagent install",  # OpenCode Ultimate · ⚠️ global npm/`npx omo`/`bunx omo` 금지 (Codex Light: `npx lazycodex-ai install`)
    "hermes": "uv tool install --python 3.11 git+https://github.com/NousResearch/hermes-agent",
    "claude": "npm i -g @anthropic-ai/claude-code",
    "codex": "npm i -g @openai/codex",
    "fake": "",                              # 내장 — 설치 불필요
}


def _bun_install_cmd() -> str:
    if sys.platform == "win32":
        return 'powershell -c "irm bun.sh/install.ps1 | iex"'
    return "curl -fsSL https://bun.sh/install | bash"


def _node_install_cmd() -> str:
    return "install Node.js LTS (https://nodejs.org) — or via nvm"


# provider → 런타임 의존성 명세(name, install_cmd, purpose). 본체와 분리.
_RUNTIME_DEPS: dict[str, list[tuple[str, Callable[[], str], str]]] = {
    "omo": [("bun", _bun_install_cmd, "omo(opencode) runtime — 미설치 시 spawnSync bun ENOENT")],
    "claude": [("node", _node_install_cmd, "Claude Code npm CLI runtime")],
    "codex": [("node", _node_install_cmd, "Codex npm CLI runtime")],
    "hermes": [],                            # standalone exe — 런타임 의존성 없음
    "fake": [],                              # 내장 — 의존성 0
}


def _default_available(name: str) -> bool:
    return shutil.which(name) is not None


# ──────────────── inspect 보조: install_hint / runtime_deps ────────────────
def install_hint_for(provider: str) -> str:
    """provider *본체* 공식 설치 명령(런타임 dep 아님). 미상은 빈 문자열."""
    return _INSTALL_HINT.get(provider, "")


def runtime_deps_for(provider: str, *, is_available: Optional[Callable[[str], bool]] = None) -> list[RuntimeDep]:
    """provider의 런타임 의존성 목록(available=PATH best-effort). 본체(install_hint)와 섞지 않는다."""
    check = is_available or _default_available
    return [RuntimeDep(name=name, available=check(name), install_cmd=cmd_fn(), purpose=purpose)
            for name, cmd_fn, purpose in _RUNTIME_DEPS.get(provider, [])]


def install_plan(provider: str, *, is_available: Optional[Callable[[str], bool]] = None) -> InstallPlan:
    return InstallPlan(provider=provider, install_hint=install_hint_for(provider),
                       runtime_deps=runtime_deps_for(provider, is_available=is_available))


def render_install_print(plan: InstallPlan) -> str:
    """print-first 출력 — '이 명령을 네 셸에서 실행하라'. dipeen이 실행하지 않는다(기본)."""
    lines = [f"{plan.provider} is not installed (or not advertised yet)."]
    missing_deps = [d for d in plan.runtime_deps if not d.available]
    if missing_deps:
        lines.append("\nRuntime dependencies first:")
        lines += [f"  {d.name}: {d.install_cmd}    # {d.purpose}" for d in missing_deps]
    if plan.install_hint:
        lines.append("\nInstall the provider (run in your own shell):")
        lines.append(f"  {plan.install_hint}")
    lines.append(f"\nThen verify (advertises capability only if healthy):")
    lines.append(f"  dipeen providers probe {plan.provider}")
    return "\n".join(lines)


# ──────────────── probe-health 게이트 (capability 광고는 healthy일 때만) ────────────────
def is_probe_healthy(provider: str, stdout: str, stderr: str, exit_code: int) -> bool:
    """provider별 parse_probe로 healthy 판정. probe 모듈 없으면(claude/codex 등) 광고 불가 → False.
    Evidence First — 설치/탐지만으론 healthy 아님. live 결과만 capability를 켠다."""
    try:
        mod = importlib.import_module(f"app.nat.providers.{provider}.probe")
    except ModuleNotFoundError:
        return False
    try:
        return bool(mod.parse_probe(stdout, stderr, exit_code).get("ok"))
    except Exception:  # noqa: BLE001 — 파싱 실패는 unhealthy로(정직)
        return False


def advertised_capability(provider: str, *, healthy: bool) -> Optional[str]:
    """healthy면 광고할 capability(provider.X), 아니면 None(광고 금지)."""
    return f"provider.{provider}" if healthy else None


# ──────────────── print-first opt-in 설치 ────────────────
def _shell_runner(cmd: str) -> int:
    """공식 설치 명령을 사용자 셸로 실행(명시적 opt-in 경로에서만 호출). 실패해도 예외 대신 exit code."""
    try:
        return subprocess.run(cmd, shell=True).returncode
    except OSError:
        return -1


def run_install(provider: str, *, execute: bool = False,
                confirm: Optional[Callable[[], bool]] = None,
                runner: Optional[Callable[[str], int]] = None,
                prober: Optional[Callable[[str], dict]] = None) -> dict:
    """print-first provider 설치.

    execute=False(기본): 공식 명령만 출력, **실행 0**.
    execute=True: interactive confirm 통과 시에만 공식 명령 대행 실행 → 설치 후 prober로 재검증.
                  confirm 거부 시 실행 안 함(안전 기본). 실패해도 호출자(worker)는 죽지 않는다.
    """
    plan = install_plan(provider)
    base = {"provider": provider, "install_hint": plan.install_hint,
            "runtime_deps": [d.name for d in plan.runtime_deps], "text": render_install_print(plan)}
    if not execute:
        return {**base, "mode": "print", "executed": False}

    # 명시적 opt-in 경로 — confirm 없으면 거부(기본 안전). third-party 명령 무조건 실행 금지.
    confirm = confirm or (lambda: False)
    if not confirm():
        return {**base, "mode": "execute", "executed": False, "aborted": True}
    if not plan.install_hint:
        return {**base, "mode": "execute", "executed": False, "reason": "no install command for provider"}
    rc = (runner or _shell_runner)(plan.install_hint)
    reprobe = (prober or (lambda _p: None))(provider)
    healthy = bool(reprobe and reprobe.get("ok"))
    return {**base, "mode": "execute", "executed": True, "exit": rc, "reprobe": reprobe,
            "advertised": advertised_capability(provider, healthy=healthy)}
