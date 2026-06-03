"""NAT 계약 + Verifier 코어 — acceptance 기계검증이 *에이전트 무관 동일 판정*인지(NAT 핵심).

State 신뢰 금지: 에이전트가 DONE 선언해도 acceptance 미충족이면 거짓 → Verifier가 잡는다.
"""
from app.schemas.nat import (
    AgentAddress, AcceptanceCriterion, Artifact, check_acceptance,
)


def test_agent_address_uri_parse():
    a = AgentAddress(role="frontend", specialty="login")
    assert a.uri == "agent://frontend/login"
    p = AgentAddress.parse("agent://backend/api")
    assert p.role == "backend" and p.specialty == "api"
    assert AgentAddress.parse("agent://research").specialty is None


def test_acceptance_all_pass():
    crit = [
        AcceptanceCriterion(kind="gitdiff_nonempty"),
        AcceptanceCriterion(kind="file_exists", target="src/components/Login.tsx"),
        AcceptanceCriterion(kind="test_passes", target="pytest"),
        AcceptanceCriterion(kind="artifact_type", target="code_patch"),
    ]
    ok, fails = check_acceptance(
        crit,
        changed_files=["src/components/Login.tsx"],
        checks={"pytest": "pass"},
        artifacts=[Artifact(type="code_patch", producer="agent://frontend", task_id="T-1")],
    )
    assert ok, fails


def test_acceptance_false_done_caught():
    """DONE 선언 + 변경 0 = 거짓. Verifier가 잡는다(이번 세션 false-done의 일반화)."""
    crit = [AcceptanceCriterion(kind="gitdiff_nonempty"),
            AcceptanceCriterion(kind="file_exists", target="src/Login.tsx")]
    ok, fails = check_acceptance(crit, changed_files=[], checks={}, artifacts=[])
    assert not ok
    assert any("gitdiff" in f for f in fails)
    assert any("file_exists" in f for f in fails)


def test_acceptance_test_fail():
    crit = [AcceptanceCriterion(kind="test_passes", target="pytest")]
    ok, fails = check_acceptance(crit, changed_files=["x.py"], checks={"pytest": "fail"})
    assert not ok and any("실패" in f for f in fails)


def test_agent_agnostic_same_verdict():
    """같은 acceptance를 Claude(git diff)·OMO(edit result) 산출물에 적용 → 동일 판정 = NAT 핵심."""
    crit = [AcceptanceCriterion(kind="file_exists", target="Login.tsx"),
            AcceptanceCriterion(kind="gitdiff_nonempty")]
    claude = check_acceptance(crit, changed_files=["src/Login.tsx"])
    omo = check_acceptance(crit, changed_files=["src/Login.tsx"])
    assert claude == omo == (True, [])


def test_state_nat_translation():
    from app.schemas.nat import to_agent_state
    assert to_agent_state("done") == "DONE"
    assert to_agent_state("in_progress") == "RUNNING"
    assert to_agent_state("rejected") == "FAILED"
    assert to_agent_state("weird") == "FAILED"        # 미지 → fail-closed


def test_artifact_nat_translation():
    from app.schemas.nat import to_artifacts
    arts = to_artifacts(
        {"task_id": "T-1", "changed_files": ["src/A.tsx", "src/B.ts"], "key_decisions": ["use Zustand"]},
        "agent://frontend",
    )
    assert len(arts) == 3
    assert sum(1 for a in arts if a.type == "code_patch") == 2
    assert any(a.type == "decision" and "Zustand" in a.summary for a in arts)
    assert all(a.producer == "agent://frontend" and a.task_id == "T-1" for a in arts)
