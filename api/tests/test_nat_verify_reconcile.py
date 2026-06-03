"""NAT M4 — Verifier(artifact evidence + acceptance) + Reconciler(증거기반 TaskState).

done-when(§ULTRAPLAN M4): false-done(claim done인데 deliverable 없음)→NEEDS_RETRY. acceptance 충족→DONE.
증거 우선(아키텍처): agent 말(StateClaim)이 아니라 남긴 산출물·증거로 Dipeen이 TaskState를 결정.
"""
import pytest

from app.nat.contracts import (
    TaskEnvelope, Artifact, ArtifactProducer, Evidence, StateClaim, PermissionRequest,
    RawAgentOutput,
)
from app.nat.core import verifier, reconciler, inbound
from app.nat import providers as _providers


@pytest.fixture(autouse=True)
def _providers_ready():
    _providers.register_defaults()
    yield


def _art(type_, *, status="produced", evidence=None, locations=None) -> Artifact:
    return Artifact(type=type_, task_id="T-1", run_id="R-1",
                    producer=ArtifactProducer(identity="agent://team/frontend", adapter="claude"),
                    status=status, evidence=evidence or [], locations=locations or [])


def _claim(state) -> StateClaim:
    return StateClaim(task_id="T-1", run_id="R-1", producer="agent://team/frontend", claimed_state=state)


def _task(acceptance=None) -> TaskEnvelope:
    return TaskEnvelope(title="t", intent="i", acceptance=acceptance or [])


def _diff_evidence():
    return [Evidence(kind="git_diff_exists", passed=True)]


# ════════ Verifier — artifact type별 evidence ════════
def test_verify_code_patch_with_diff_is_verified():
    a = verifier.verify_artifact(_art("code_patch", evidence=_diff_evidence()))
    assert a.status == "verified"


def test_verify_code_patch_without_diff_is_rejected():
    a = verifier.verify_artifact(_art("code_patch", evidence=[Evidence(kind="git_diff_exists", passed=False)]))
    assert a.status == "rejected"


def test_verify_command_receipt_needs_no_special_evidence():
    assert verifier.verify_artifact(_art("command_receipt")).status == "verified"


def test_verify_does_not_mutate_input():
    a = _art("code_patch", evidence=_diff_evidence())
    verifier.verify_artifact(a)
    assert a.status == "produced"        # 원본 불변(사본 반환)


# ════════ Verifier — acceptance(증거로 기계검증) ════════
def test_acceptance_artifact_required_met_by_verified():
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    verified = verifier.verify_artifacts([_art("code_patch", evidence=_diff_evidence())])
    ok, fails = verifier.check_acceptance(task, artifacts=verified)
    assert ok and not fails


def test_acceptance_artifact_required_missing_fails():
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    ok, fails = verifier.check_acceptance(task, artifacts=[verifier.verify_artifact(_art("command_receipt"))])
    assert not ok and any("code_patch" in f for f in fails)


def test_acceptance_file_required_matches_file_change_set():
    from app.nat.contracts import ArtifactLocation
    task = _task([{"type": "file_required", "path": "src/app/login/page.tsx"}])
    fcs = _art("file_change_set", evidence=_diff_evidence(),
               locations=[ArtifactLocation(uri="file:///ws/src/app/login/page.tsx")])
    ok, _ = verifier.check_acceptance(task, artifacts=verifier.verify_artifacts([fcs]))
    assert ok


def test_acceptance_command_required_uses_checks():
    task = _task([{"type": "command_required", "command": "npm test", "must_pass": True}])
    ok_pass, _ = verifier.check_acceptance(task, artifacts=[], checks={"npm test": "pass"})
    ok_fail, fails = verifier.check_acceptance(task, artifacts=[], checks={"npm test": "fail"})
    assert ok_pass and not ok_fail


def test_acceptance_empty_requires_deliverable_baseline():
    # 명시 기준 없으면 command_receipt만으론 부족(거짓 done 차단)
    only_receipt = [verifier.verify_artifact(_art("command_receipt"))]
    ok, _ = verifier.check_acceptance(_task([]), artifacts=only_receipt)
    assert not ok
    with_patch = verifier.verify_artifacts([_art("code_patch", evidence=_diff_evidence())])
    ok2, _ = verifier.check_acceptance(_task([]), artifacts=with_patch)
    assert ok2


# ════════ Reconciler — 최종 TaskState ════════
def test_reconcile_done_when_acceptance_met():
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    arts = [_art("code_patch", evidence=_diff_evidence())]
    assert reconciler.reconcile(task, claims=[_claim("done")], artifacts=arts).state == "DONE"


def test_reconcile_false_done_to_needs_retry():
    # claim done인데 deliverable 없음(command_receipt만) → NEEDS_RETRY
    r = reconciler.reconcile(_task([]), claims=[_claim("done")], artifacts=[_art("command_receipt")])
    assert r.state == "NEEDS_RETRY" and r.failure_type == "artifact_missing"


def test_reconcile_awaiting_permission_takes_precedence():
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    arts = [_art("code_patch", evidence=_diff_evidence())]
    perm = PermissionRequest(task_id="T-1", run_id="R-1", requester="agent://team/frontend",
                             action="git.push", requires_human_approval=True)
    r = reconciler.reconcile(task, claims=[_claim("done")], artifacts=arts, permissions=[perm])
    assert r.state == "AWAITING_PERMISSION"      # acceptance 충족이어도 승인 먼저


def test_reconcile_blocked_and_failed_claims():
    assert reconciler.reconcile(_task([]), claims=[_claim("blocked")], artifacts=[]).state == "BLOCKED"
    f = reconciler.reconcile(_task([]), claims=[_claim("failed")], artifacts=[])
    assert f.state == "FAILED"


def test_reconcile_evidence_first_done_overrides_failed_claim():
    # 증거 우선: agent가 failed라 해도 acceptance 충족이면 DONE
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    arts = [_art("code_patch", evidence=_diff_evidence())]
    assert reconciler.reconcile(task, claims=[_claim("failed")], artifacts=arts).state == "DONE"


# ════════ 통합 — M3 inbound → M4 reconcile (전체 증거 파이프라인) ════════
def test_integration_inbound_then_reconcile_done():
    raw = RawAgentOutput(run_id="R-1", identity_id="agent://team/frontend", exit_code=0,
                         stdout="done", changed_files=["src/app/login/page.tsx"], workspace_root="/ws")
    res = inbound.normalize(raw, provider="claude", task_id="T-1")
    task = _task([{"type": "artifact_required", "artifact_type": "code_patch"}])
    assert reconciler.reconcile(task, claims=res.state_claims, artifacts=res.artifacts).state == "DONE"


def test_integration_inbound_false_done_then_reconcile_retry():
    # exit 0(→claim done)인데 변경 없음 → inbound은 command_receipt만 → 거짓 done 차단
    raw = RawAgentOutput(run_id="R-2", identity_id="agent://team/frontend", exit_code=0,
                         stdout="i did nothing", changed_files=[], workspace_root="/ws")
    res = inbound.normalize(raw, provider="codex", task_id="T-1")
    assert res.state_claims[0].claimed_state == "done"
    assert reconciler.reconcile(_task([]), claims=res.state_claims, artifacts=res.artifacts).state == "NEEDS_RETRY"
