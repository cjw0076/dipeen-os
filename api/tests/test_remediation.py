"""RemediationPolicy(decide_remediation) — 순수 결정 함수 테스트 + A3 비평가 가드."""
from app.schemas.runner import GatekeeperVerdict
from app.services.remediation import decide_remediation


def _v(verdict, code, reason="r"):
    return GatekeeperVerdict(task_id="T", verdict=verdict, failure_code=code, reason=reason)


def test_accept_passthrough():
    assert decide_remediation(_v("accept", "NONE")).action == "accept"


def test_scope_violation_fail_closed_to_human():
    # 자동화 금지 — 범위 위반은 항상 사람.
    d = decide_remediation(_v("needs_human", "SCOPE_VIOLATION"))
    assert d.action == "needs_human"


def test_hitl_and_unknown_fail_closed():
    assert decide_remediation(_v("needs_human", "HITL_REQUIRED")).action == "needs_human"
    assert decide_remediation(_v("reject", "UNKNOWN")).action == "needs_human"   # 신규 = fail-closed


def test_cancelled_stops():
    assert decide_remediation(_v("reject", "CANCELLED")).action == "stop"


def test_promise_false_retries_then_exhausts():
    # PROMISE_FALSE max_retries=2 → attempt 1,2는 retry, 3은 소진→사람.
    d1 = decide_remediation(_v("reject", "PROMISE_FALSE"), attempt=1)
    assert d1.action == "retry" and d1.attempt == 2 and d1.packet
    d3 = decide_remediation(_v("reject", "PROMISE_FALSE"), attempt=3)
    assert d3.action == "needs_human"


def test_deterministic_fail_one_retry():
    # DETERMINISTIC_FAIL max_retries=1 → attempt 1은 retry, 2는 소진.
    assert decide_remediation(_v("reject", "DETERMINISTIC_FAIL"), attempt=1).action == "retry"
    assert decide_remediation(_v("reject", "DETERMINISTIC_FAIL"), attempt=2).action == "needs_human"


def test_progress_monotonicity_guard():
    # ② 직전과 *같은 사유*로 또 실패 → 결정론적 실패 → 재시도 말고 사람.
    d = decide_remediation(_v("reject", "PROMISE_FALSE", reason="same"),
                           attempt=1, prev_reason="same")
    assert d.action == "needs_human" and "같은 사유" in d.reason


def test_packet_has_no_rubric():
    # Remediation Packet은 사유+증거만 — 통과 체크리스트(rubric) 노출 금지(reward hacking 방지).
    d = decide_remediation(_v("reject", "PROMISE_FALSE", reason="미충족"), attempt=1)
    assert "REMEDIATION" in d.packet and "MUST_NOT" in d.packet


def test_runner_error_to_human():
    assert decide_remediation(_v("reject", "RUNNER_ERROR")).action == "needs_human"


def test_ambiguous_done_decompose():
    assert decide_remediation(_v("reject", "AMBIGUOUS_DONE")).action == "decompose"


def test_recurrence_advisory_in_reason():
    # 재발(>=3)은 reason에 fixture 권고로만 실린다(관측 전용 — 보상신호 아님).
    d = decide_remediation(_v("needs_human", "SCOPE_VIOLATION"), recurrence=3)
    assert "fixture" in d.reason
