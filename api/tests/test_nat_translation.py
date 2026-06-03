"""NAT M3 — Outbound(TaskEnvelope→AgentInvocation) + Inbound(RawAgentOutput→NormalizedAgentResult).

done-when(§ULTRAPLAN M3): 같은 TaskEnvelope를 Claude·Codex로 → raw output 달라도 Dipeen 내부엔
**동일 Artifact 타입/shape**(에이전트무관). Core(outbound/inbound)는 provider를 모르고 registry로 위임한다.
"""
import pytest

from app.nat.contracts import (
    TaskEnvelope, TaskScope, AgentIdentity, AgentBinding, AgentInvocation,
    RawAgentOutput, NormalizedAgentResult,
)
from app.nat.core import outbound, inbound, registry
from app.nat import providers as _providers


@pytest.fixture(autouse=True)
def _ensure_providers():
    _providers.register_defaults()        # idempotent — claude/codex 플러그인 등록
    yield


def _task() -> TaskEnvelope:
    return TaskEnvelope(
        title="Implement login", intent="로그인 화면 구현",
        scope=TaskScope(repo="ezmap", paths=["src/app/login"]),
        constraints=["Do not change backend API"],
        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}],
    )


def _identity(adapter: str) -> AgentIdentity:
    return AgentIdentity(identity_id="agent://team/frontend", role="frontend",
                         binding=AgentBinding(adapter=adapter))


def _raw(stdout: str, *, run_id="R-1", exit_code=0, changed=("src/app/login/page.tsx",)) -> RawAgentOutput:
    return RawAgentOutput(run_id=run_id, identity_id="agent://team/frontend", exit_code=exit_code,
                          stdout=stdout, changed_files=list(changed), workspace_root="/ws/ezmap")


# ════════ registry — Core가 이름으로 위임(provider 미인지) ════════
def test_registry_resolves_known_and_rejects_unknown():
    assert registry.get_plugin("claude").name == "claude"
    assert registry.get_plugin("codex").name == "codex"
    with pytest.raises(KeyError):
        registry.get_plugin("nonexistent")


# ════════ Outbound — TaskEnvelope → AgentInvocation ════════
def test_build_invocation_renders_task_into_prompt():
    inv = outbound.build_invocation(_task(), _identity("claude"),
                                    run_id="R-1", workspace_root="/ws/ezmap")
    assert isinstance(inv, AgentInvocation)
    assert inv.run_id == "R-1" and inv.identity_id == "agent://team/frontend"
    assert inv.workspace_root == "/ws/ezmap"
    assert "로그인 화면 구현" in inv.prompt              # intent
    assert "Do not change backend API" in inv.prompt     # constraint


def test_build_invocation_provider_divergence_subscription_vs_byok():
    """provider별 to_invocation: claude=구독 기본(키 unset) / codex=login 기반. shape는 동일."""
    ic = outbound.build_invocation(_task(), _identity("claude"), run_id="R-1", workspace_root="/ws")
    ix = outbound.build_invocation(_task(), _identity("codex"), run_id="R-2", workspace_root="/ws")
    assert ic.env.get("ANTHROPIC_API_KEY") == ""         # 구독 크레딧0(M2 adapter가 ""→unset)
    assert "ANTHROPIC_API_KEY" not in ix.env
    assert type(ic) is type(ix)                          # 동일 타입


# ════════ Inbound — RawAgentOutput → NormalizedAgentResult ════════
def test_inbound_changed_files_become_code_patch_and_file_change_set():
    res = inbound.normalize(_raw("claude done"), provider="claude", task_id="T-1")
    assert isinstance(res, NormalizedAgentResult)
    types = {a.type for a in res.artifacts}
    assert "code_patch" in types and "file_change_set" in types
    cp = next(a for a in res.artifacts if a.type == "code_patch")
    assert cp.task_id == "T-1" and cp.run_id == "R-1"
    assert cp.producer.identity == "agent://team/frontend"
    assert any(e.kind == "git_diff_exists" and e.passed for e in cp.evidence)
    fcs = next(a for a in res.artifacts if a.type == "file_change_set")
    assert any("page.tsx" in loc.uri for loc in fcs.locations)


def test_inbound_stdout_becomes_command_receipt():
    res = inbound.normalize(_raw("build ok\nexit 0"), provider="codex", task_id="T-1")
    assert any(a.type == "command_receipt" for a in res.artifacts)


def test_inbound_state_claim_from_exit_code():
    done = inbound.normalize(_raw("ok"), provider="claude", task_id="T-1")
    assert done.state_claims and done.state_claims[0].claimed_state == "done"
    failed = inbound.normalize(_raw("boom", exit_code=1, changed=()), provider="codex", task_id="T-1")
    assert failed.state_claims[0].claimed_state == "failed"


def test_inbound_emits_normalized_events():
    res = inbound.normalize(_raw("x"), provider="claude", task_id="T-1")
    kinds = {e.event_type for e in res.events}
    assert "artifact.produced" in kinds and "state.claimed" in kinds


# ════════ M3 done-when: 에이전트 무관 Artifact shape ════════
def test_same_task_claude_codex_yield_same_artifact_shape():
    task = _task()
    # 같은 task → provider별 invocation(프롬프트는 달라도 됨)
    outbound.build_invocation(task, _identity("claude"), run_id="R-1", workspace_root="/ws")
    outbound.build_invocation(task, _identity("codex"), run_id="R-2", workspace_root="/ws")
    # raw는 provider마다 포맷 상이(claude=json stream / codex=텍스트) — 같은 changed_files
    raw_c = _raw('{"type":"result","subtype":"success"}', run_id="R-1")
    raw_x = _raw("codex: applied patch to src/app/login/page.tsx", run_id="R-2")
    res_c = inbound.normalize(raw_c, provider="claude", task_id="T-1")
    res_x = inbound.normalize(raw_x, provider="codex", task_id="T-1")

    def shape(res):
        return sorted(
            (a.type, len(a.locations) > 0, tuple(sorted(e.kind for e in a.evidence)))
            for a in res.artifacts
        )

    assert shape(res_c) == shape(res_x)                              # raw 달라도 동일 shape
    assert sorted(a.type for a in res_c.artifacts) == sorted(a.type for a in res_x.artifacts)


# ════════ Isolation — Core는 provider를 import하지 않는다 ════════
def test_core_does_not_import_provider_plugins():
    import app.nat.core.outbound as ob
    import app.nat.core.inbound as ib
    import app.nat.core.registry as rg
    for m in (ob, ib, rg):
        for forbidden in ("ClaudeNATPlugin", "CodexNATPlugin"):
            assert not hasattr(m, forbidden), f"Isolation 위반: {m.__name__} exposes {forbidden}"
