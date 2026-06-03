"""RemediationPolicy — failure_code → action 매핑 (LLM 없음). OCDR 루프의 *Decide*.

원칙(`docs/agent-failure-recovery-architecture.md §6` + 비평가(A3) 가드):
- retry는 메커니즘이 아니라 분류 후 *라우팅의 한 분기*다. 기본은 보수적(fail-closed).
- bounded retry 종료조건 (하나라도 위반 → human gate):
  ① 하드 상한 N≤2  ② 진전 단조성(직전과 *같은 사유* 반복 → 결정론적 실패 → gate)
  ③ 표면 불변(재시도가 검증 자산을 건드리면 안 됨 — Packet의 MUST_NOT + 다음 게이트가 차단)
  ④ 신규/UNKNOWN/범위/고위험 → fail-closed(사람).
- Remediation Packet은 *사유+증거*만 준다. *통과 기준(rubric)*은 노출하지 않는다(reward hacking 방지).
- recurrence(재발 카운터)는 *관측용*으로만 reason에 실어 사람에게 보인다(보상신호 X — Goodhart).
- 이 모듈은 순수(IO·LLM 없음) → 결정론적·테스트 가능.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas.runner import GatekeeperVerdict

# failure_code → 최대 자동 재시도 횟수. 없는 코드는 자동 재시도 안 함.
_RETRYABLE: dict[str, int] = {
    "PROMISE_FALSE": 2,
    "DETERMINISTIC_FAIL": 1,
    "TIMEOUT": 1,
    "STALE_EDIT": 2,
}
# 자동화 금지 — 항상 사람(fail-closed).
_HUMAN = {"SCOPE_VIOLATION", "HITL_REQUIRED", "UNKNOWN"}
# 자동 재개 없음(종료).
_TERMINAL = {"CANCELLED"}


@dataclass
class RemediationDecision:
    action: str            # accept | retry | needs_human | decompose | stop
    attempt: int           # retry일 때 다음 시도 번호
    failure_code: str
    reason: str
    packet: Optional[str] = None   # retry 시 envelope.prompt에 append (rubric 없음)


def decide_remediation(
    verdict: GatekeeperVerdict,
    attempt: int = 1,
    prev_reason: Optional[str] = None,
    recurrence: int = 0,
) -> RemediationDecision:
    """Gatekeeper 판정 → 다음 행동. attempt=현재까지 시도한 횟수(1=최초)."""
    code = verdict.failure_code
    rc = f" (이 실패가 팀에서 {recurrence}회 재발 — 반복되면 프롬프트 땜질 말고 eval fixture 박제+구조 수정 1회)" if recurrence >= 3 else ""

    if verdict.verdict == "accept":
        return RemediationDecision("accept", attempt, code, "ok")
    if code in _HUMAN:
        return RemediationDecision("needs_human", attempt, code, f"fail-closed: 사람 판정 필요{rc}")
    if code in _TERMINAL:
        return RemediationDecision("stop", attempt, code, "취소됨 — 재개 없음")

    max_r = _RETRYABLE.get(code)
    if max_r is None:
        if code == "AMBIGUOUS_DONE":
            return RemediationDecision("decompose", attempt, code, f"부분 완료 — PM이 wave 분해{rc}")
        return RemediationDecision("needs_human", attempt, code, f"자동 복구 정책 없음 → 사람{rc}")

    # ① 하드 상한 (max_r = 최대 *재시도* 횟수. attempt=현재 시도 번호, 1=최초)
    if attempt > max_r:
        return RemediationDecision("needs_human", attempt, code,
                                   f"자동 재시도 소진(attempt {attempt}, max_retries {max_r}) → 사람{rc}")
    # ② 진전 단조성: 직전과 같은 사유 = 결정론적 실패 → retry 무의미
    if prev_reason is not None and verdict.reason == prev_reason:
        return RemediationDecision("needs_human", attempt, code,
                                   f"같은 사유 반복(결정론적 실패) → 사람{rc}")

    next_attempt = attempt + 1
    return RemediationDecision("retry", next_attempt, code, "bounded 재시도",
                               packet=_build_packet(verdict, next_attempt, max_r))


def _build_packet(verdict: GatekeeperVerdict, attempt: int, max_r: int) -> str:
    """다음 시도의 *태스크 envelope에만* append. 전역 시스템 프롬프트 수정 아님.
    사유+증거만 — judge의 통과 체크리스트는 주지 않는다(LLM이 문제 대신 judge를 풀지 않도록)."""
    checks = ", ".join(f"{k}:{v}" for k, v in (verdict.deterministic_checks or {}).items()) or "n/a"
    return (
        f"## REMEDIATION (attempt {attempt}/{max_r})\n"
        f"- failure_code: {verdict.failure_code}\n"
        f"- 이전 시도가 Gatekeeper에서 거부됨. 사유: {verdict.reason or 'n/a'}\n"
        f"- 결정론 검증: {checks}\n"
        f"- MUST_DO: 위 사유를 *실제로* 해소한 뒤 .dipeen-result.json에 completion_promise=DONE.\n"
        f"- MUST_NOT: 테스트/검증 자산을 수정하거나, 같은 변경만 반복하고 완료라고 보고하지 말 것."
    )
