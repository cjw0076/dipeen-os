"""Epic B — Runner contract (RunReport 추적성 + canonical-done discipline).

RunReport(=RawAgentOutput)는 worker가 제출하는 *실행 증거*다 — runner/command/cwd/worker_id로
"누가·무엇을·어디서·어느 노드에서" 실행했는지 재현(replay) 가능해야 한다(Epic F portable bundle 입력).

규칙(state machine이 흔들리지 않도록 고정):
  - Runner는 claim만 제출한다 — canonical done은 Reconciler가 소유(StateClaim ≠ TaskState).
  - artifact 누락 = needs_retry (거짓 done 금지).
  - unknown CLI flag = runner_error(정직한 비0 exit) — 가짜 success로 덮지 않는다(silent fallback 금지).
"""
from __future__ import annotations

import pytest

from app.nat.adapters.base import CliExecAdapter, ExecResult, default_runner
from app.nat.adapters.omo import OmoAdapter
from app.nat.contracts import (
    AgentBinding, AgentIdentity, AgentInvocation, StateClaim, TaskEnvelope,
)
from app.nat.core.reconciler import reconcile


# ──────────────── 헬퍼 ────────────────
def _runner(exit_code: int = 0, stdout: str = "", stderr: str = ""):
    """주입형 CommandRunner — CLI 없이 결정론적 ExecResult를 낸다(hermetic)."""
    async def run(argv, *, cwd, env, timeout_sec):
        return ExecResult(exit_code, stdout, stderr)
    return run


class _Echo(CliExecAdapter):
    name = "echo"
    cli = "echo"

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        return ["echo", invocation.prompt]


def _inv(ws: str) -> AgentInvocation:
    return AgentInvocation(run_id="R-1", identity_id="agent://team/echo",
                           prompt="hi", workspace_root=ws)


def _task_needs_patch() -> TaskEnvelope:
    return TaskEnvelope(title="t", intent="fix",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}])


# ═══════════════ Part 1: RunReport 추적성 (runner/command/cwd/worker_id) ═══════════════
@pytest.mark.asyncio
async def test_run_report_records_runner_command_cwd(tmp_path):
    """RawAgentOutput=RunReport: 어떤 runner가 어떤 command를 어느 cwd에서 실행했는지 남는다(replay 입력)."""
    raw = await _Echo(runner=_runner(0, "ok")).run(_inv(str(tmp_path)))
    assert raw.runner == "echo"                       # 실행기 식별(adapter.name)
    assert raw.command == ["echo", "hi"]              # 실제 argv(번역 아님, 그대로)
    assert raw.cwd == str(tmp_path)                   # 실행 디렉토리


@pytest.mark.asyncio
async def test_run_override_provider_inherits_trace_fields(tmp_path):
    """run을 오버라이드하는 provider(omo/hermes)도 super().run 경유로 추적 필드를 상속한다."""
    raw = await OmoAdapter(runner=_runner(0, '{"success": true, "summary": "done"}')).run(_inv(str(tmp_path)))
    assert raw.runner == "omo"
    assert "run" in raw.command and "--json" in raw.command   # omo run … --json


@pytest.mark.asyncio
async def test_worker_execute_stamps_worker_id(tmp_path):
    """worker_id는 adapter가 아니라 *실행 노드*가 RunReport에 찍는다(어느 머신에서 돌았나)."""
    from app.nat.core.pipeline import worker_execute
    task = TaskEnvelope(title="t", intent="hi")
    identity = AgentIdentity(identity_id="agent://team/fake", role="fake",
                             binding=AgentBinding(adapter="fake"))
    _, raw, _ = await worker_execute(task, identity, run_id="R-1",
                                     workspace_root=str(tmp_path), worker_id="worker.minjun")
    assert raw.worker_id == "worker.minjun"


# ═══════════════ Part 2: canonical-done discipline (M4 규칙 고정) ═══════════════
def test_runner_done_claim_without_evidence_is_not_canonical_done():
    """Runner가 done을 *주장*해도 evidence 없으면 canonical DONE 아님 — Reconciler가 소유."""
    task = _task_needs_patch()
    claim = StateClaim(task_id=task.task_id, run_id="R-1",
                       producer="agent://team/echo", claimed_state="done")
    result = reconcile(task, claims=[claim], artifacts=[])
    assert result.state == "NEEDS_RETRY"              # done claim ≠ DONE
    assert result.state != "DONE"


def test_missing_artifact_is_needs_retry_not_done():
    """acceptance가 artifact 요구인데 산출물 0 → needs_retry(artifact_missing), done 아님."""
    result = reconcile(_task_needs_patch(), claims=[], artifacts=[])
    assert result.state == "NEEDS_RETRY"
    assert result.failure_type == "artifact_missing"


# ═══════════════ Part 3: unknown flag = runner_error, not silent fallback ═══════════════
@pytest.mark.asyncio
async def test_unknown_flag_surfaces_honest_nonzero_exit(tmp_path):
    """unknown CLI flag → 정직한 비0 exit(runner_error). 어댑터가 가짜 success 이벤트로 덮지 않는다."""
    raw = await OmoAdapter(runner=_runner(2, "", "error: unknown option '--nope'")).run(_inv(str(tmp_path)))
    assert raw.exit_code == 2                          # 정직한 비0(runner_error)
    assert raw.raw_events == []                        # 가짜 success 합성 0 (silent fallback 금지)


@pytest.mark.asyncio
async def test_missing_binary_is_honest_127_not_fabricated_success():
    """누락 바이너리 → default_runner가 정직하게 127 보고(완료 조작 금지)."""
    res = await default_runner(["dipeen-nonexistent-binary-zzz"], cwd=".", env={}, timeout_sec=10)
    assert res.exit_code == 127
    assert "not found" in res.stderr.lower()
