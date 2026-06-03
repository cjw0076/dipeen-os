"""NAT contracts (§21 step1) — 계약 타입 구성 + 판별 union(acceptance) + Adapter/NAT 경계 타입 검증."""
from app.nat.contracts import (
    AgentIdentity, AgentBinding, TaskEnvelope, TaskScope, Run, StateClaim,
    Artifact, ArtifactProducer, ArtifactLocation, Evidence, ArtifactLink,
    PermissionRequest, MemoryCandidate, RawAgentOutput, NormalizedAgentResult,
)


def test_identity():
    i = AgentIdentity(identity_id="agent://team/frontend", role="frontend",
                      binding=AgentBinding(adapter="claude", runtime="claude-code"))
    assert i.binding.adapter == "claude" and i.trust_level == "sandboxed"


def test_task_envelope_discriminated_acceptance():
    t = TaskEnvelope(
        title="Implement login", intent="로그인 화면",
        scope=TaskScope(repo="dipeen", paths=["src/app/login"]),
        acceptance=[
            {"type": "artifact_required", "artifact_type": "code_patch"},
            {"type": "command_required", "command": "npm test", "must_pass": True},
            {"type": "file_required", "path": "src/app/login/page.tsx"},
        ],
    )
    assert t.task_id.startswith("T-") and t.state == "CREATED"
    assert [c.type for c in t.acceptance] == ["artifact_required", "command_required", "file_required"]
    assert t.acceptance[1].command == "npm test"        # 판별 union → 올바른 타입
    assert t.acceptance[2].path.endswith("page.tsx")


def test_artifact_rich():
    a = Artifact(
        type="code_patch", task_id="T-1", run_id="R-1",
        producer=ArtifactProducer(identity="agent://team/frontend", adapter="claude", provider="anthropic"),
        title="login patch",
        locations=[ArtifactLocation(uri="file://ws/A-1/diff.patch", sha256="abc", media_type="text/x-diff")],
        evidence=[Evidence(kind="git_diff_exists", passed=True), Evidence(kind="test_passed", passed=True)],
        links=[ArtifactLink(relation="implements", target_type="task", target_id="T-1")],
    )
    assert a.artifact_id.startswith("A-") and a.status == "produced"
    assert all(e.passed for e in a.evidence)


def test_state_claim_vs_run():
    r = Run(task_id="T-1", identity_id="agent://team/frontend", attempt=2)
    sc = StateClaim(task_id="T-1", run_id=r.run_id, producer="agent://team/frontend", claimed_state="done")
    assert r.attempt == 2 and sc.claimed_state == "done"   # claim ≠ TaskState(Reconciler 결정)


def test_permission_and_memory():
    p = PermissionRequest(task_id="T-1", run_id="R-1", requester="agent://team/frontend",
                          action="git.push", target="github://cjw/dipeen", reason="push branch")
    assert p.requires_human_approval and p.state == "requested"
    m = MemoryCandidate(memory_type="project_decision", proposed_content="use existing auth API")
    assert m.promotion_policy == "requires_review"         # 자동 승격 금지


def test_adapter_nat_boundary():
    raw = RawAgentOutput(run_id="R-1", identity_id="agent://team/frontend", exit_code=0,
                         changed_files=["src/app/login/page.tsx"])
    norm = NormalizedAgentResult()
    assert raw.changed_files and norm.artifacts == []      # Adapter=raw만, NAT가 normalized 채움
