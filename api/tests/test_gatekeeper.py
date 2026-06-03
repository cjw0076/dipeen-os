"""Gatekeeper(출구 게이트) 단위 테스트 — scope_claims 강제 + runner 자기보고 불신."""
from app.schemas.runner import TaskEnvelope, RunReport, ScopeClaims
from app.services.gatekeeper import gatekeep


def _env(**scope) -> TaskEnvelope:
    return TaskEnvelope(task_id="T-1", team_id="t", subject="s", prompt="p",
                        scope_claims=ScopeClaims(**scope))


def _rep(**kw) -> RunReport:
    base = dict(task_id="T-1", agent_id="a", runner="claude-code", status="done", completion_promise="DONE")
    base.update(kw)
    return RunReport(**base)


def test_accept_clean():
    v = gatekeep(_env(), _rep(changed_files=["web/x.tsx"], scope_diff=["web/x.tsx"]), {"pytest": "pass", "ruff": "pass"})
    assert v.verdict == "accept" and not v.scope_violations


def test_reject_check_failed():
    v = gatekeep(_env(), _rep(scope_diff=["web/x.tsx"]), {"pytest": "fail"})
    assert v.verdict == "reject"


def test_reject_error_status():
    v = gatekeep(_env(), _rep(status="error", blockers=["boom"]))
    assert v.verdict == "reject"


def test_needs_human_deny_path():
    # runner가 .env를 만짐 → deny_path 위반 → 사람에게 (카드 재사용)
    v = gatekeep(_env(deny_paths=[".env"]), _rep(changed_files=[".env"], scope_diff=[".env"]), {"pytest": "pass"})
    assert v.verdict == "needs_human" and v.scope_violations and v.human_card_prompt


def test_needs_human_outside_allow():
    v = gatekeep(_env(allow_paths=["web/**"]), _rep(scope_diff=["api/secret.py"]), {"pytest": "pass"})
    assert v.verdict == "needs_human"


def test_needs_human_high_risk():
    v = gatekeep(_env(requires_human_approval=True), _rep(scope_diff=["web/x"]), {"pytest": "pass"})
    assert v.verdict == "needs_human"


def test_reject_promise_not_met():
    # runner가 DONE을 자기보고 안 함 → HQ가 reject (자기보고 불신)
    v = gatekeep(_env(), _rep(completion_promise=None, scope_diff=["web/x"]), {"pytest": "pass"})
    assert v.verdict == "reject"


def test_max_files_exceeded():
    v = gatekeep(_env(max_files=2), _rep(changed_files=["a", "b", "c"], scope_diff=["a", "b", "c"]), {"pytest": "pass"})
    assert v.verdict == "needs_human"


def test_failure_code_mapping():
    # 각 분기가 올바른 FailureCode로 분류되는지 (RemediationPolicy의 키)
    assert gatekeep(_env(), _rep(scope_diff=["web/x"]), {"pytest": "pass"}).failure_code == "NONE"
    assert gatekeep(_env(), _rep(status="error", blockers=["boom"])).failure_code == "RUNNER_ERROR"
    assert gatekeep(_env(), _rep(status="cancelled")).failure_code == "CANCELLED"
    assert gatekeep(_env(), _rep(scope_diff=["web/x"]), {"pytest": "fail"}).failure_code == "DETERMINISTIC_FAIL"
    assert gatekeep(_env(deny_paths=[".env"]), _rep(scope_diff=[".env"])).failure_code == "SCOPE_VIOLATION"
    assert gatekeep(_env(), _rep(completion_promise=None, scope_diff=["web/x"])).failure_code == "PROMISE_FALSE"
    assert gatekeep(_env(requires_human_approval=True), _rep(scope_diff=["web/x"])).failure_code == "HITL_REQUIRED"
