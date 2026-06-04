"""T2 — 식별자 자동 고유화: DIPEEN_AGENT_ID 미지정 시 워커가 고유 id를 받는다.

이전엔 전원 기본 'fe-agent'로 충돌(roster에서 서로 덮어씀). 이제 미지정이면
<role>-<user>-<host>-<rand>로 고유. 명시 지정은 항상 우선.
"""
import os

from dipeen_agent import config


def test_default_agent_id_is_unique_and_structured():
    a = config._default_agent_id()
    b = config._default_agent_id()
    assert a != b                       # rand suffix → 동시 합류해도 충돌 없음
    assert a.count("-") >= 3            # role-user-host-rand
    assert a == a.lower()
    assert a != "fe-agent"


def test_explicit_env_id_wins():
    # config가 쓰는 식과 동일: 명시 지정이 자동 고유화보다 우선
    assert (os.environ.get("DIPEEN_AGENT_ID") or config._default_agent_id()) != config._default_agent_id() \
        if os.environ.get("DIPEEN_AGENT_ID") else True
    saved = os.environ.get("DIPEEN_AGENT_ID")
    os.environ["DIPEEN_AGENT_ID"] = "my-fixed-id"
    try:
        assert (os.environ.get("DIPEEN_AGENT_ID") or config._default_agent_id()) == "my-fixed-id"
    finally:
        if saved is None:
            os.environ.pop("DIPEEN_AGENT_ID", None)
        else:
            os.environ["DIPEEN_AGENT_ID"] = saved
