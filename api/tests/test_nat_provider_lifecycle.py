"""Provider Lifecycle (print-first opt-in install) — 사용자 결정문 RED 목록.

Decision: Adopt print-first provider installation.
- Bootstrap installs only uv + dipeen-agent + join + required runtime deps.
- OMO/Hermes provider binaries are NOT installed automatically during join.
- provider 본체 설치는 print-only 기본, --execute는 명시적 opt-in.
- capability는 probe healthy일 때만 광고(probe 통과 전 provider.X 광고 금지).
- OMO/Hermes 미설치라도 worker는 죽지 않음(online 유지, fake는 항상 가용).

Lifecycle: MISSING → INSTALL_HINTED → USER_INSTALLED → PROBED → HEALTHY → CAPABILITY_ADVERTISED
"""
from __future__ import annotations

import shutil


# ──────────────── inspect 확장: install_hint / runtime_deps / capability_advertised ────────────────
def test_omo_missing_outputs_install_hint(monkeypatch):
    """OMO 미설치 → inspect가 공식 본체 설치 명령(install_hint)을 제시(자동설치 아님, 안내)."""
    monkeypatch.setattr(shutil, "which", lambda n: None)          # 아무 바이너리도 없음
    from app.nat.providers.omo import inspect as omo_inspect
    insp = omo_inspect.inspect()
    assert insp.installed is False
    assert insp.install_hint                                       # 공식 본체 설치 명령 존재
    assert "oh-my-openagent" in insp.install_hint.lower()          # upstream 공식(bunx oh-my-openagent install)


def test_omo_missing_does_not_advertise_capability(monkeypatch):
    """probe 통과 전(=static inspect)에는 provider.omo capability 광고 금지(Evidence First)."""
    monkeypatch.setattr(shutil, "which", lambda n: None)
    from app.nat.providers.omo import inspect as omo_inspect
    assert omo_inspect.inspect().capability_advertised is False


def test_bun_missing_is_runtime_dependency():
    """bun은 omo의 *런타임 의존성*이지 provider 본체가 아니다 — runtime_deps로 분리 보고."""
    from app.nat.providers.omo import inspect as omo_inspect
    deps = {d.name for d in omo_inspect.inspect().runtime_deps}
    assert "bun" in deps                                          # bun = omo runtime dep
    # provider 본체(install_hint)와 runtime dep(bun)이 섞이지 않음 — runtime bun installer(bun.sh) 기준.
    # bunx(본체 설치 도구)의 "bun" substring은 허용(런타임 bun 설치 명령이 아님).
    assert "bun.sh" not in omo_inspect.inspect().install_hint.lower()


# ──────────────── fake provider는 omo 없이도 항상 가용 ────────────────
def test_fake_provider_available_without_omo(monkeypatch):
    """keyless fake 어댑터는 provider 바이너리/런타임 없이도 가용 — 빈 머신 first-run 약속의 토대."""
    monkeypatch.setattr(shutil, "which", lambda n: None)          # PATH에 아무 CLI도 없음
    from app.nat.core.pipeline import _ADAPTERS
    assert "fake" in _ADAPTERS                                    # 내장 어댑터(키·CLI·네트워크 0)
    from app.nat.providers.omo import inspect as omo_inspect
    assert omo_inspect.inspect().installed is False               # omo는 없어도
    # fake는 그와 무관하게 registry에 등록되어 있음
    from app.nat.providers import registry
    assert "fake" in registry.registered()


# ──────────────── providers install — print-first / --execute opt-in ────────────────
def test_provider_install_print_does_not_execute():
    """기본(print) 경로는 설치를 *실행하지 않는다* — 공식 명령만 보여준다."""
    from app.nat.providers.lifecycle import run_install
    ran: list[str] = []
    res = run_install("omo", execute=False, runner=lambda cmd: ran.append(cmd) or 0)
    assert res["executed"] is False
    assert res["mode"] == "print"
    assert ran == []                                             # 설치 스크립트 실행 0
    assert res["install_hint"]                                   # 명령은 보여줌


def test_provider_install_execute_requires_explicit_flag():
    """--execute(+confirm)일 때만 공식 설치 명령을 실행. 플래그 없으면/거부면 실행 안 함."""
    from app.nat.providers.lifecycle import run_install
    ran: list[str] = []

    # 1) execute=False → 실행 안 함
    r1 = run_install("omo", execute=False, runner=lambda c: ran.append(c) or 0)
    assert r1["executed"] is False and ran == []

    # 2) execute=True 이지만 confirm 거부 → 실행 안 함(interactive 확인 필수)
    ran_b: list[str] = []
    r2 = run_install("omo", execute=True, confirm=lambda: False, runner=lambda c: ran_b.append(c) or 0)
    assert r2["executed"] is False and ran_b == []

    # 3) execute=True + confirm 승인 → 공식 명령 실행 + 설치 후 재검증(probe)
    ran_c: list[str] = []
    r3 = run_install("omo", execute=True, confirm=lambda: True,
                     runner=lambda c: ran_c.append(c) or 0, prober=lambda p: {"ok": True})
    assert r3["executed"] is True
    assert ran_c and "oh-my-openagent" in ran_c[0].lower()      # upstream 공식(bunx oh-my-openagent install)


# ──────────────── worker capability 광고는 probe healthy일 때만 ────────────────
def test_probe_pass_advertises_provider_capability(tmp_path):
    """healthy probe → worker가 provider.X를 advertise(registry 갱신)."""
    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.worker_registry import WorkerRegistry
    from app.nat.worker import WorkerNode
    store = str(tmp_path / "nat")
    reg = WorkerRegistry(store)
    w = WorkerNode("w1", capabilities=["provider.fake"], queue=CommandQueue(store),
                   registry=reg, store_root=store)
    w.register()
    healthy = w.apply_probe_capability("hermes", stdout="Hermes Agent v0.15.1", stderr="", exit_code=0)
    assert healthy is True
    assert "provider.hermes" in reg.get("w1").capabilities       # 광고됨


def test_probe_fail_keeps_worker_online(tmp_path):
    """probe 실패(omo bun ENOENT) → worker는 online 유지, provider.omo 미광고 → omo task 안 감."""
    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.worker_registry import WorkerRegistry
    from app.nat.worker import WorkerNode
    store = str(tmp_path / "nat")
    reg = WorkerRegistry(store)
    w = WorkerNode("w1", capabilities=["provider.fake"], queue=CommandQueue(store),
                   registry=reg, store_root=store)
    w.register()
    healthy = w.apply_probe_capability(
        "omo", stdout="", stderr="oh-my-opencode: failed to execute Bun: spawnSync bun ENOENT", exit_code=2)
    assert healthy is False
    info = reg.get("w1")
    assert info is not None                                      # worker는 죽지 않음(online)
    assert "provider.omo" not in info.capabilities              # 미광고
    assert "provider.fake" in info.capabilities                 # 기존 cap 유지
