"""Gatekeeper (W1) — wrap 경계의 *출구 게이트*.

원칙(`docs/dipeen-wrap-principle.md`): 완료는 runner 자기보고가 아니라 HQ가 판정한다.
결정 카드(entry gate)가 고정한 `scope_claims`를 RunReport가 지켰는지 + 결정론 검증(pytest/ruff)을
통과했는지 확인 → accept | reject | needs_human.

needs_human이면 HQ가 결정 카드를 *다시* 사람에게 띄운다(카드 = 입구·출구 공용 인간 인터페이스).
이 모듈은 순수 함수(LLM·IO 없음) → 결정론적·테스트 가능.
"""
from __future__ import annotations

import fnmatch

from app.schemas.runner import TaskEnvelope, RunReport, GatekeeperVerdict


def _matches(path: str, pattern: str) -> bool:
    p = path.replace("\\", "/").lstrip("./")
    pat = pattern.replace("\\", "/").lstrip("./")
    return fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.rstrip("/") + "/*") or p == pat


def _passed(v: object) -> bool:
    return v in (True, "pass", "ok", "passed", 0, "0")


def gatekeep(
    envelope: TaskEnvelope,
    report: RunReport,
    checks: dict | None = None,
) -> GatekeeperVerdict:
    """RunReport를 envelope의 경계 + 결정론 검증에 비춰 판정한다.

    checks 예: {"pytest": "pass", "ruff": "pass"}  (Node 또는 HQ가 실행한 결정론 도구 결과)
    """
    sc = envelope.scope_claims
    checks = checks or {}
    violations: list[str] = []

    touched = report.scope_diff or report.changed_files

    # 1) deny_paths — 절대 금지 (.env, secrets 등)
    for path in touched:
        for deny in sc.deny_paths:
            if _matches(path, deny):
                violations.append(f"deny_path 위반: {path} (deny={deny})")

    # 2) allow_paths — 허용 목록이 있으면 그 안이어야
    if sc.allow_paths:
        for path in touched:
            if not any(_matches(path, a) for a in sc.allow_paths):
                violations.append(f"allow_paths 밖 편집: {path}")

    # 3) max_files
    if sc.max_files is not None and len(report.changed_files) > sc.max_files:
        violations.append(f"max_files 초과: {len(report.changed_files)} > {sc.max_files}")

    failed = [k for k, v in checks.items() if not _passed(v)]

    def verdict(v, code="NONE", reason=None, human=None):
        return GatekeeperVerdict(
            task_id=envelope.task_id, verdict=v, failure_code=code, deterministic_checks=checks,
            scope_violations=violations, reason=reason, human_card_prompt=human,
        )

    # ── 판정 순서: 명백한 실패 → 범위/고위험(사람) → 통과 ── (각 분기는 failure_code로 분류)
    if report.status == "error":
        return verdict("reject", "RUNNER_ERROR", reason=f"runner error: {'; '.join(report.blockers) or 'unknown'}")
    if report.status == "cancelled":
        return verdict("reject", "CANCELLED", reason="cancelled")
    if failed:
        return verdict("reject", "DETERMINISTIC_FAIL", reason=f"결정론 검증 실패: {failed}")
    if violations:
        return verdict("needs_human", "SCOPE_VIOLATION", reason="scope_claims 위반",
                       human=f"태스크 {envelope.task_id}가 승인 범위를 벗어났습니다. 검토 필요:\n- " + "\n- ".join(violations))
    if report.completion_promise != envelope.completion_promise:
        return verdict("reject", "PROMISE_FALSE", reason=f"완료 약속 미충족(promise={report.completion_promise!r})")
    if sc.requires_human_approval:
        return verdict("needs_human", "HITL_REQUIRED", reason="고위험 — 사람 승인 필요",
                       human=f"태스크 {envelope.task_id} 완료. 고위험 변경이라 승인이 필요합니다.")
    return verdict("accept", "NONE")
