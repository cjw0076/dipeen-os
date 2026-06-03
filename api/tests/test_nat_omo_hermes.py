"""M11c·d·e OMO/Hermes NAT 통합 — outbound render · adapter · inbound 변환.

clone 분석(omo 4.7.4 / hermes 최신) 기반: omo run --json=RunResult, event stream=message-updated/
tool-execute/session-idle. hermes memory_tool/skill_manage=파일 side-effect. canned는 실제 소스 스키마.
금지: subtask→Task 금지(provider.subtask Event), memory auto-promote 금지(requires_review), StateClaim≠TaskState.
"""
import json
import subprocess

import pytest


# ──────────────── Task 5: contract 갭 (SkillCandidate / context_evidence / EventType / skill_candidates) ────────────────
def test_skill_candidate_defaults_requires_review():
    from app.nat.contracts import SkillCandidate
    s = SkillCandidate(name="dedupe-logs", description="merge duplicate log lines")
    assert s.promotion_policy == "requires_review"          # 자동승격 금지(memory와 동일 정책)
    assert s.skill_candidate_id.startswith("S-CAND")
    assert s.confidence == 0.5


def test_context_evidence_artifact_type():
    from app.nat.contracts import Artifact, ArtifactProducer
    a = Artifact(type="context_evidence", task_id="T-1",
                 producer=ArtifactProducer(identity="agent://team/hermes"))
    assert a.type == "context_evidence"


def test_normalized_result_has_skill_candidates():
    from app.nat.contracts import NormalizedAgentResult
    r = NormalizedAgentResult()
    assert r.skill_candidates == []


def test_event_provider_subtask_and_checkpoint():
    from app.nat.contracts import Event
    assert Event(event_type="provider.subtask", producer="x").event_type == "provider.subtask"
    assert Event(event_type="long_task.checkpoint", producer="x").event_type == "long_task.checkpoint"


# ──────────────── Task 6-8: OMO inbound parsers (raw_events → 계약, 독립) ────────────────
def _omo_raw(events):
    from app.nat.contracts import RawAgentOutput
    return RawAgentOutput(run_id="R-1", identity_id="agent://team/omo", exit_code=0, raw_events=events)


def test_omo_team_message_maps_to_room_message():
    from app.nat.providers.omo.inbound_events import omo_events
    raw = _omo_raw([{"kind": "message", "from": "lead", "to": "fe", "content": "구현해줘"}])
    evs = omo_events(raw, task_id="T-1", artifacts=[])
    msg = [e for e in evs if e.event_type == "discussion.message"]
    assert msg and "구현해줘" in msg[0].message


def test_omo_subtask_stays_provider_local():
    from app.nat.providers.omo.subtask_mapping import subtask_events
    raw = _omo_raw([{"kind": "task", "task_id": "tsk_1", "status": "pending", "title": "FE work"}])
    evs = subtask_events(raw, task_id="T-1")
    assert evs and evs[0].event_type == "provider.subtask"        # Dipeen Task 아님 — Event로만
    assert evs[0].payload.get("provider_task_id") == "tsk_1"
    assert evs[0].task_id == "T-1"                                # parent 참조(새 Task/Run 생성 아님)


def test_omo_review_maps_to_review_result_artifact():
    from app.nat.providers.omo.inbound_artifacts import omo_artifacts
    raw = _omo_raw([{"kind": "review", "verdict": "approved", "content": "LGTM"}])
    arts = omo_artifacts(raw, task_id="T-1")
    rev = [a for a in arts if a.type == "review_result"]
    assert rev and "LGTM" in rev[0].summary


def test_omo_final_maps_to_state_claim_not_task_state():
    from app.nat.providers.omo.state_claims import omo_state_claims
    raw = _omo_raw([{"kind": "final", "success": True, "summary": "done"}])
    claims = omo_state_claims(raw, task_id="T-1")
    assert claims and claims[0].claimed_state == "done"           # *주장*일 뿐
    assert not hasattr(claims[0], "task_state")                   # TaskState 필드 없음(Reconciler가 결정)


# ──────────────── Task 9-10: Hermes inbound parsers (파일/hook 스키마 → 계약) ────────────────
def _hermes_raw(events):
    from app.nat.contracts import RawAgentOutput
    return RawAgentOutput(run_id="R-2", identity_id="agent://team/hermes", exit_code=0, raw_events=events)


def test_hermes_memory_write_maps_to_memory_candidate():
    from app.nat.providers.hermes.memory_candidate import hermes_memory_candidates
    raw = _hermes_raw([{"kind": "memory_write", "action": "add", "target": "memory", "content": "use uv for python"}])
    cands = hermes_memory_candidates(raw)
    assert cands and "use uv" in cands[0].proposed_content


def test_hermes_skill_maps_to_skill_candidate():
    from app.nat.providers.hermes.skill_candidate import hermes_skill_candidates
    raw = _hermes_raw([{"kind": "skill_create", "name": "dedupe-logs", "content": "merge dup lines"}])
    cands = hermes_skill_candidates(raw)
    assert cands and cands[0].name == "dedupe-logs"


def test_hermes_memory_does_not_auto_promote():
    from app.nat.providers.hermes.memory_candidate import hermes_memory_candidates
    raw = _hermes_raw([{"kind": "memory_write", "action": "add", "content": "x"}])
    assert hermes_memory_candidates(raw)[0].promotion_policy == "requires_review"   # 자동승격 금지


def test_hermes_long_task_maps_to_checkpoint_event():
    from app.nat.providers.hermes.long_task import hermes_long_task_events
    raw = _hermes_raw([{"kind": "cron_checkpoint", "job_id": "j1", "output": "tick 1"}])
    evs = hermes_long_task_events(raw, task_id="T-1")
    assert evs and evs[0].event_type == "long_task.checkpoint"
    assert (evs[0].payload or {}).get("job_id") == "j1"


def test_hermes_retrieval_maps_to_context_evidence():
    from app.nat.providers.hermes.context_retrieval import context_evidence_artifacts
    raw = _hermes_raw([{"kind": "retrieval", "query": "past auth bug", "results": ["fix in authz.py"]}])
    arts = context_evidence_artifacts(raw, task_id="T-1")
    assert arts and arts[0].type == "context_evidence"


# ──────────────── Task 1 + 11: plugin + register + normalize ────────────────
def test_omo_hermes_registered():
    from app.nat.core.registry import get_plugin
    from app.nat.providers import register_defaults
    register_defaults()
    assert get_plugin("omo").name == "omo"
    assert get_plugin("hermes").name == "hermes"


def test_omo_to_invocation_renders_prompt():
    from app.nat.contracts import TaskEnvelope
    from app.nat.providers.omo import OmoNATPlugin
    inv = OmoNATPlugin().to_invocation(TaskEnvelope(title="t", intent="fix login"),
                                       run_id="R", identity_id="agent://team/omo", workspace_root="/ws")
    assert "fix login" in inv.prompt


def test_omo_normalize_end_to_end():
    from app.nat.core.inbound import normalize
    raw = _omo_raw([{"kind": "message", "from": "lead", "to": "fe", "content": "go"},
                    {"kind": "final", "success": True, "summary": "done"}])
    result = normalize(raw, provider="omo", task_id="T-1")
    assert any(e.event_type == "discussion.message" for e in result.events)
    assert result.state_claims and result.state_claims[0].claimed_state == "done"


def test_hermes_normalize_skill_and_memory():
    from app.nat.core.inbound import normalize
    raw = _hermes_raw([{"kind": "memory_write", "action": "add", "content": "use uv"},
                       {"kind": "skill_create", "name": "dedupe", "content": "x"}])
    result = normalize(raw, provider="hermes", task_id="T-1")
    assert result.memory_candidates and "use uv" in result.memory_candidates[0].proposed_content
    assert result.skill_candidates and result.skill_candidates[0].name == "dedupe"


# ──────────────── Task 2: CLI providers render (dry-run, no exec) ────────────────
def test_cli_render_omo_no_exec(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 0, "", ""))
    from app.nat.cli import main
    rc = main(["providers", "render", "omo", "fix login", "--workspace", str(tmp_path)])
    assert rc == 0
    assert calls == []                                    # render는 실행 0(dry-run preview)
    assert "fix login" in capsys.readouterr().out


# ──────────────── Task 3: OmoAdapter / HermesAdapter (실측 시도 + 정직) ────────────────
@pytest.mark.asyncio
async def test_omo_adapter_argv():
    from app.nat.adapters.omo import OmoAdapter
    from app.nat.contracts import AgentInvocation
    argv = OmoAdapter().argv_for(AgentInvocation(run_id="R", identity_id="i", prompt="do x", workspace_root="/ws"))
    assert "run" in argv and "--json" in argv and "do x" in argv


@pytest.mark.asyncio
async def test_omo_adapter_normalizes_runresult(tmp_path):
    from app.nat.adapters.base import ExecResult
    from app.nat.adapters.omo import OmoAdapter
    from app.nat.contracts import AgentInvocation

    class FakeRunner:
        async def __call__(self, argv, *, cwd, env, timeout_sec):
            return ExecResult(0, '{"success": true, "summary": "ok", "sessionId": "s"}', "")
    raw = await OmoAdapter(runner=FakeRunner()).run(
        AgentInvocation(run_id="R", identity_id="i", prompt="x", workspace_root=str(tmp_path)))
    assert raw.raw_events and raw.raw_events[0]["kind"] == "final" and raw.raw_events[0]["success"] is True


@pytest.mark.asyncio
async def test_hermes_adapter_oneshot_argv():
    from app.nat.adapters.hermes import HermesAdapter
    from app.nat.contracts import AgentInvocation
    argv = HermesAdapter().argv_for(AgentInvocation(run_id="R", identity_id="i", prompt="hi", workspace_root="."))
    assert "-z" in argv and "hi" in argv


@pytest.mark.asyncio
async def test_omo_adapter_bun_failure_honest(tmp_path):
    from app.nat.adapters.base import ExecResult
    from app.nat.adapters.omo import OmoAdapter
    from app.nat.contracts import AgentInvocation

    class FailRunner:
        async def __call__(self, argv, *, cwd, env, timeout_sec):
            return ExecResult(1, "", "spawnSync bun ENOENT")
    raw = await OmoAdapter(runner=FailRunner()).run(
        AgentInvocation(run_id="R", identity_id="i", prompt="x", workspace_root=str(tmp_path)))
    assert raw.exit_code == 1 and raw.raw_events == []    # 정직 — 실행 실패면 가짜 이벤트 0
