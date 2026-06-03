"""CLI provider 공유 번역 로직 (M3).

claude/codex는 M2 어댑터가 이미 RawAgentOutput(stdout/exit/changed_files)로 *정규화*해 주므로
inbound 파싱이 동일하다 → 여기 공유. provider 고유 분기(구독 env, 미래의 raw_events 포맷)는
각 provider 모듈에 남긴다. OMO/Hermes(M6/M7)는 raw_events가 풍부 → 자기 파서를 별도로 갖는다.

매핑(사용자 명세): changed_files→CODE_PATCH+FILE_CHANGE_SET / stdout→COMMAND_RECEIPT / exit→StateClaim.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import (
    Artifact, ArtifactLocation, ArtifactProducer, Evidence, Event, RawAgentOutput,
    StateClaim, TaskEnvelope,
)


# ── Outbound: TaskEnvelope → prompt 텍스트(provider 무관) ──
def _acceptance_text(c) -> str:
    if c.type == "artifact_required":
        return f"artifact 산출: {c.artifact_type}"
    if c.type == "command_required":
        return f"명령 통과: {c.command} (must_pass={c.must_pass})"
    if c.type == "file_required":
        return f"파일 존재: {c.path}"
    return str(c)


def render_task_prompt(task: TaskEnvelope, *, context_pack: Optional[str] = None) -> str:
    """TaskEnvelope를 에이전트 지시문으로 렌더. provider별 헤더는 각 plugin이 덧붙인다."""
    lines = [f"# Task: {task.title}", "", task.intent.strip(), ""]
    if task.scope.paths:
        lines += ["## Scope", *[f"- {p}" for p in task.scope.paths], ""]
    if task.constraints:
        lines += ["## Constraints", *[f"- {c}" for c in task.constraints], ""]
    if task.acceptance:
        lines += ["## Acceptance (완료 기준 — Dipeen이 증거로 검증)",
                  *[f"- {_acceptance_text(c)}" for c in task.acceptance], ""]
    if context_pack:
        lines += ["## Context", context_pack.strip(), ""]
    return "\n".join(lines).rstrip() + "\n"


# ── Inbound: RawAgentOutput → Artifact[] / StateClaim[] / Event[] ──
def cli_artifacts(raw: RawAgentOutput, *, task_id: str, adapter: str) -> list[Artifact]:
    """changed_files→CODE_PATCH+FILE_CHANGE_SET, stdout→COMMAND_RECEIPT. 에이전트 무관 동일 shape."""
    producer = ArtifactProducer(identity=raw.identity_id, adapter=adapter)
    ws = raw.workspace_root or ""
    arts: list[Artifact] = []

    if raw.changed_files:
        diff_present = Evidence(kind="git_diff_exists", passed=True)
        arts.append(Artifact(
            type="code_patch", task_id=task_id, run_id=raw.run_id, producer=producer,
            title="code patch", summary=f"{len(raw.changed_files)} file(s) changed",
            locations=[ArtifactLocation(uri=f"git://{ws}#working")],
            evidence=[diff_present],
        ))
        arts.append(Artifact(
            type="file_change_set", task_id=task_id, run_id=raw.run_id, producer=producer,
            title="file change set", summary=", ".join(raw.changed_files[:8]),
            locations=[ArtifactLocation(uri=f"file://{ws}/{f}") for f in raw.changed_files],
            evidence=[diff_present],
        ))

    receipt = (raw.stdout or "").strip()
    arts.append(Artifact(
        type="command_receipt", task_id=task_id, run_id=raw.run_id, producer=producer,
        title="command receipt", summary=receipt[:200],
        evidence=[Evidence(kind="exit_zero", passed=(raw.exit_code == 0))],
    ))
    return arts


def cli_state_claims(raw: RawAgentOutput, *, task_id: str) -> list[StateClaim]:
    """exit_code → claimed_state(주장일 뿐 — TaskState는 M4 Reconciler가 증거로 결정)."""
    claimed = "done" if raw.exit_code == 0 else "failed"
    return [StateClaim(
        task_id=task_id, run_id=raw.run_id, producer=raw.identity_id,
        claimed_state=claimed, message=f"exit_code={raw.exit_code}",
    )]


def cli_events(raw: RawAgentOutput, *, task_id: str, artifacts: list[Artifact]) -> list[Event]:
    """raw 실행을 공통 Event로(append-only). CLI는 raw_events가 비어 합성; OMO/Hermes는 자기 파서."""
    producer = raw.identity_id
    events: list[Event] = [Event(event_type="agent.started", task_id=task_id, run_id=raw.run_id,
                                 producer=producer)]
    for a in artifacts:
        events.append(Event(event_type="artifact.produced", task_id=task_id, run_id=raw.run_id,
                            producer=producer, message=a.type, payload={"artifact_id": a.artifact_id}))
    events.append(Event(event_type="state.claimed", task_id=task_id, run_id=raw.run_id,
                       producer=producer, message=("done" if raw.exit_code == 0 else "failed")))
    events.append(Event(event_type="agent.stopped", task_id=task_id, run_id=raw.run_id, producer=producer))
    return events
