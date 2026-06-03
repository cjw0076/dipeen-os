"""Verifier (M4 / §9) — artifact evidence + acceptance를 *증거로* 기계검증. Gatekeeper(라이브검증) 후신.

"State 신뢰 금지"의 실체: agent가 done이라 *주장*해도 evidence/acceptance가 미충족이면 거짓 →
Reconciler가 NEEDS_RETRY로 보낸다. 에이전트 종류(Claude/Codex/OMO) 무관 **동일 판정**(NAT 핵심).
순수(IO 없음) — 결정론적·테스트 가능. v0 `schemas/nat.py:check_acceptance` 로직을 v1 contracts shape로 포팅.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import Artifact, TaskEnvelope

# artifact type이 verified가 되려면 통과해야 하는 evidence kind(없으면 produced로 충분)
_REQUIRED_EVIDENCE: dict[str, str] = {
    "code_patch": "git_diff_exists",
    "file_change_set": "git_diff_exists",
    "test_report": "test_passed",
    "pr_reference": "executor_success",        # M7: permission receipt — executor 성공해야 verified
    "issue_reference": "executor_success",
}
# 산출물로 치지 않는 타입(로그/텔레메트리) — 명시 acceptance 없을 때 baseline에서 제외
_NON_DELIVERABLE = {"command_receipt", "metric"}


def _passed(v: object) -> bool:
    return v in (True, "pass", "ok", "passed", 0, "0")


def verify_artifact(artifact: Artifact) -> Artifact:
    """artifact type별 필수 evidence 평가 → status verified|rejected. 원본 불변(사본 반환)."""
    required = _REQUIRED_EVIDENCE.get(artifact.type)
    if required is None:
        status = "verified"
    elif any(e.kind == required and e.passed for e in artifact.evidence):
        status = "verified"
    else:
        status = "rejected"
    return artifact.model_copy(update={"status": status})


def verify_artifacts(artifacts: list[Artifact]) -> list[Artifact]:
    return [verify_artifact(a) for a in artifacts]


def has_deliverable(artifacts: list[Artifact]) -> bool:
    """verified 산출물(command_receipt/metric 제외)이 1개 이상인가 — 거짓 done 판별의 기준."""
    return any(a.status == "verified" and a.type not in _NON_DELIVERABLE for a in artifacts)


def _changed_paths(artifacts: list[Artifact]) -> list[str]:
    out: list[str] = []
    for a in artifacts:
        if a.type == "file_change_set":
            out += [loc.uri.split("://", 1)[-1].replace("\\", "/") for loc in a.locations]
    return out


def check_acceptance(task: TaskEnvelope, *, artifacts: list[Artifact],
                     checks: Optional[dict] = None) -> tuple[bool, list[str]]:
    """v1 acceptance(artifact_required/command_required/file_required)를 *verified* 증거로 기계검증.

    명시 기준이 없으면 baseline = deliverable 1개 이상(거짓 done 차단 — gatekeeper PROMISE_FALSE 선례).
    반환: (전부통과?, 실패사유[]).
    """
    checks = checks or {}
    verified = [a for a in artifacts if a.status == "verified"]

    if not task.acceptance:
        if not has_deliverable(verified):
            return (False, ["기본 기준: deliverable artifact 없음(거짓 done 차단)"])
        return (True, [])

    changed = _changed_paths(verified)
    failures: list[str] = []
    for c in task.acceptance:
        if c.type == "artifact_required":
            if not any(a.type == c.artifact_type for a in verified):
                failures.append(f"artifact_required: {c.artifact_type}(verified) 없음")
        elif c.type == "file_required":
            t = c.path.replace("\\", "/")
            if not any(p == t or p.endswith(t) for p in changed):
                failures.append(f"file_required: {c.path} 미변경")
        elif c.type == "command_required":
            if c.must_pass and not _passed(checks.get(c.command)):
                failures.append(f"command_required: {c.command} 미통과")
    return (not failures, failures)
