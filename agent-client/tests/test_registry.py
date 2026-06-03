"""W0/W2/W5/W6 — RunnerAdapter 레지스트리 + 선택 + health 검증.

이 머신엔 omo/codex/hermes 바이너리가 없으므로 health는 available=False로 *정직하게* 나와야 한다
(미설치를 설치된 척하지 않는다 — oracle 정합).
"""
import asyncio

from dipeen_agent.runners import (
    RUNNER_NAMES,
    all_health,
    get_adapter,
    resolve_runner_name,
)


def test_get_adapter_mapping():
    assert get_adapter("claude-code").name == "claude-code"
    assert get_adapter("omo-opencode").name == "omo-opencode"
    assert get_adapter("omo-codex-light").name == "omo-codex-light"
    assert get_adapter("hermes").name == "hermes"
    assert get_adapter("unknown-xyz").name == "claude-code"   # fail-safe 기본


def test_resolve_runner_name():
    assert resolve_runner_name({"runner": "hermes"}, {}) == "hermes"
    assert resolve_runner_name({"runner": "omo-codex-light"}, {}) == "omo-codex-light"
    # 모르는/없는 runner → 기본 후보(RUNNER_NAMES 내)
    assert resolve_runner_name({"runner": "bogus"}, {}) in RUNNER_NAMES
    assert resolve_runner_name({}, {}) in RUNNER_NAMES


def test_all_health_enumerates_all_runners():
    healths = asyncio.run(all_health())
    assert {h.name for h in healths} == set(RUNNER_NAMES)
    for h in healths:
        assert isinstance(h.available, bool)   # 미설치면 False(정직)
        assert h.line()                        # doctor 출력 한 줄
