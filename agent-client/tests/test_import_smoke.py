"""패키징/임포트 스모크 — 빈 머신에서 다운로드한 사용자가 첫 명령에서 ImportError로 막히는 것을 차단.

근거(E2E 2026-06-04, finding #9): 공개 스냅샷(dipeen-os)에 `onboarding.py`는 포함됐지만
그것이 import하는 `support_levels.py`가 누락 → `dipeen-agent doctor/connect/join` 전부 ImportError 크래시.
shipped 모듈 하나라도 누락되면(curation/패키징 drift) 이 테스트가 유저보다 먼저 실패한다.
"""
from __future__ import annotations

import importlib
import pkgutil

import dipeen_agent


def _shipped_modules() -> list[str]:
    """패키지가 ship하는 모든 모듈 이름. `__main__`은 import 시 run()을 실행하므로 제외."""
    names = []
    for m in pkgutil.walk_packages(dipeen_agent.__path__, dipeen_agent.__name__ + "."):
        if m.name.rsplit(".", 1)[-1] == "__main__":
            continue
        names.append(m.name)
    return names


def test_every_shipped_module_imports():
    """shipped 모듈 전부가 import 가능해야 한다(누락된 내부 의존 모듈 = 패키징 drift)."""
    failures: list[str] = []
    modules = _shipped_modules()
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — 어떤 import 실패든 패키징 결함으로 보고
            failures.append(f"{name}: {exc!r}")
    assert modules, "패키지 모듈을 하나도 못 찾았다 — walk_packages/패키징 회귀"
    assert not failures, "import 불가 모듈(패키징 drift):\n" + "\n".join(failures)


def test_support_levels_is_shipped():
    """finding #9 회귀 가드: onboarding이 의존하는 support_levels가 패키지에 포함돼야 한다."""
    assert "dipeen_agent.support_levels" in _shipped_modules()
    from dipeen_agent import onboarding  # `from .support_levels import runner_support`로 의존
    assert callable(onboarding.runner_support)


def test_documented_onboarding_command_handlers_resolve():
    """문서화된 dipeen-agent 온보딩 서브커맨드 → onboarding 핸들러가 callable로 존재.

    main.run()의 dispatch 표와 일치(doctor/setup/connect/join→connect/bootstrap/runner install).
    핸들러가 사라지거나 onboarding이 import 불가가 되면 여기서 잡힌다.
    """
    from dipeen_agent import onboarding

    # 서브커맨드 → onboarding 속성명 (join은 connect 재사용, runner install은 install_runner)
    for command, attr in [
        ("doctor", "doctor"),
        ("setup", "setup"),
        ("connect", "connect"),
        ("join", "connect"),
        ("bootstrap", "bootstrap"),
        ("runner install", "install_runner"),
    ]:
        handler = getattr(onboarding, attr, None)
        assert callable(handler), f"`dipeen-agent {command}` 핸들러 onboarding.{attr} 누락/비callable"
