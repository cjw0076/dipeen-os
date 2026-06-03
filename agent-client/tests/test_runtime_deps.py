"""런타임 의존성(bun 등) — installer는 얇게, 설치는 Python onboarding이 담당.

원칙(spec one_touch_bootstrap): 감지/설치는 OS 분기·dry_run·멱등이 가능한 Python에. 셸(install.*)은
uv+dipeen-agent+join만. setup이 러너 설치 *전에* 누락 런타임(omo→bun)을 설치한다.
"""
import os
import platform
import shutil
import subprocess
import sys

from dipeen_agent import onboarding


# ──────────────────── Task 1: RuntimeDependency 모델 + bun 레지스트리 ────────────────────
def test_runtime_dep_bun_present_skips_install(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/bun" if n == "bun" else None)
    dep = onboarding.get_runtime_dep("bun")
    assert dep is not None
    assert dep.installed() is True


def test_runtime_dep_bun_missing_adds_install_plan(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    monkeypatch.setattr(onboarding.os.path, "exists", lambda p: False)
    missing = onboarding.missing_runtime_deps(["bun"])
    assert [d.id for d in missing] == ["bun"]


def test_windows_bun_install_command(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    assert "bun.sh/install.ps1" in onboarding.get_runtime_dep("bun").install_cmd()


def test_unix_bun_install_command(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert "https://bun.sh/install" in onboarding.get_runtime_dep("bun").install_cmd()


# ──────────────────── Task 2: install_runtime_dep ────────────────────
def test_install_runtime_dep_dry_run_no_exec(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(onboarding.subprocess, "run", lambda *a, **k: called.append(a) or None)
    dep = onboarding.get_runtime_dep("bun")
    rc = onboarding.install_runtime_dep(dep, dry_run=True)
    assert rc == 0
    assert called == []                      # dry_run은 실행 안 함
    assert "bun" in capsys.readouterr().out  # 명령은 출력


def test_install_runtime_dep_appends_env_paths(monkeypatch):
    monkeypatch.setattr(onboarding.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0))
    monkeypatch.setenv("PATH", "/usr/bin")
    dep = onboarding.get_runtime_dep("bun")
    onboarding.install_runtime_dep(dep, dry_run=False)
    assert os.path.expanduser("~/.bun/bin") in onboarding.os.environ["PATH"]


# ──────────────────── Task 3: runner runtime_deps + provisioning ────────────────────
def test_omo_runner_requires_bun():
    from dipeen_agent.runners import provisioning
    p = provisioning()
    assert "bun" in p["omo-opencode"]["runtime_deps"]      # opencode=bun 기반
    assert p["omo-codex-light"]["runtime_deps"] == []      # codex CLI 기반 — bun 불필요
    assert p["claude-code"]["runtime_deps"] == []          # claude는 런타임 의존 없음


def test_runner_runtime_deps_union_dedup():
    deps = onboarding.runner_runtime_deps(["omo-opencode", "omo-codex-light", "claude-code"])
    assert deps == ["bun"]                              # 합집합, 순서 보존, dedup


# ──────────────────── Task 4: setup print-first (런타임 자동, 본체 opt-in) ────────────────────
def test_setup_installs_runtime_but_not_runner_body(monkeypatch):
    """print-first 계약(2026-06-03): 런타임 dep(bun)은 자동 설치되지만 provider *본체*(runner)는
    자동 설치하지 않는다 — install_hint만 안내(`runner install`로 opt-in). join도 이 경로를 탄다."""
    from dipeen_agent.runners import RunnerHealth
    order = []
    monkeypatch.setattr(onboarding, "install_runtime_dep",
                        lambda dep, dry_run=False: order.append(f"runtime:{dep.id}") or 0)
    monkeypatch.setattr(onboarding, "install_runner",
                        lambda name, dry_run=False: order.append(f"runner:{name}") or 0)
    monkeypatch.setattr(onboarding, "all_health",
                        lambda: [RunnerHealth("omo-opencode", False, "x")])
    monkeypatch.setattr(onboarding.asyncio, "run", lambda coro: coro)  # all_health(동기) 결과 그대로
    monkeypatch.setattr(onboarding, "missing_runtime_deps",
                        lambda ids: [onboarding.get_runtime_dep("bun")] if ids else [])
    onboarding.setup(auto_install=True, dry_run=True)
    assert "runtime:bun" in order                              # 런타임 dep는 자동(멱등)
    assert not any(o.startswith("runner:") for o in order)     # provider 본체는 자동 설치 안 함(print-first)


def test_setup_dry_run_still_returns_zero():
    assert onboarding.setup(auto_install=False, dry_run=True) == 0   # 기존 계약 보존


# ──────────────────── Task 5: bootstrap dry-run bun plan + join reuse ────────────────────
def test_bootstrap_dry_run_prints_bun_plan(tmp_path, capsys):
    rc = onboarding.bootstrap(role="FE", workspace=str(tmp_path / "ws"),
                              network="cloudflare", dry_run=True, env_path=tmp_path / ".env")
    assert rc == 0
    assert "bun" in capsys.readouterr().out      # 런타임 계획에 bun 노출


def test_join_uses_existing_setup_path(monkeypatch):
    """join은 새 설치 로직을 만들지 않고 기존 connect→setup 경로를 재사용한다."""
    calls = []
    monkeypatch.setattr(onboarding, "connect",
                        lambda url, api_url=None, run_setup=True: calls.append(("connect", run_setup)) or 0)
    import dipeen_agent.main as m
    monkeypatch.setattr(sys, "argv", ["dipeen-agent", "join", "https://hq/join?code=X", "--no-setup"])
    try:
        m.run()
    except SystemExit:
        pass
    assert any(c[0] == "connect" for c in calls)
