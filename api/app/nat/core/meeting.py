"""Meeting Closure (4단계 / Core) — 회의방 메시지를 분류해 후보를 만든다. **승인 전엔 작업 아님.**

회의에서 나온 모든 말을 task로 만들지 않는다. decision/task/permission/memory/question으로 나누고,
사람이 승인한 것만 실행 객체가 된다(action→CommandProposal, decision→record, memory→promote).
v0 분류기=규칙 기반(키워드). 추후 LLM 분류기가 같은 인터페이스(classify_message)로 대체 가능.
핵심 연결: action candidate 승인 → CommandProposal(배정) → Assignment Routing → Workspace → worker.
"""
from __future__ import annotations

from ..contracts import (ActionCandidate, AssignmentSpec, CommandProposal, DecisionCandidate,
                         Event, MeetingClosurePacket, MemoryCandidate, Message)
from . import proposals
from .eventlog import EventLog

# 분류 마커(우선순위 순). build verb가 decision marker보다 우선(구현하자=task). 추후 LLM 분류기로 대체.
_MEMORY = ("기억", "remember", "기록해", "잊지")
_PERMISSION = ("해도 돼", "해도돼", "승인", "push", "deploy", "배포", "pr 만들", "pr만들", "권한")
_BUILD = ("구현", "만들", "개발", "작성", "리팩터", "고쳐", "수정", "implement", "build", "create", "fix")
_DECISION = ("쓰자", "하자", "가자", "낫겠", "채택", "결정", "쓰는 게", "use ", "쓴다")
_QUESTION_W = ("뭐야", "왜", "어떻게", "어디", "언제", "원인")


def classify_message(body: str) -> str:
    """메시지 → category(memory/permission/task/decision/question/note). plain=note(후보 아님)."""
    t = (body or "").lower()
    if any(k in t for k in _MEMORY):
        return "memory"
    if any(k in t for k in _PERMISSION):
        return "permission"
    if any(k in t for k in _BUILD):
        return "task"
    if any(k in t for k in _DECISION):
        return "decision"
    if t.strip().endswith("?") or any(k in t for k in _QUESTION_W):
        return "question"
    return "note"


def close_meeting(room_id: str, messages: list[Message]) -> MeetingClosurePacket:
    """회의방 메시지를 분류해 정리물을 만든다. typed proposal은 바로 task/decision 후보. **후보만, 실행 0.**"""
    packet = MeetingClosurePacket(room_id=room_id)
    for m in messages:
        if m.message_type == "command.proposal":
            cat = "task"
        elif m.message_type == "decision.proposal":
            cat = "decision"
        else:
            cat = classify_message(m.body)
        if cat == "task":
            packet.task_candidates.append(ActionCandidate(
                source_message_ids=[m.message_id], title=m.body[:48], intent=m.body))
        elif cat == "decision":
            packet.decisions.append(DecisionCandidate(source_message_ids=[m.message_id], statement=m.body))
        elif cat == "memory":
            packet.memory_candidates.append(MemoryCandidate(
                memory_type="project_decision", proposed_content=m.body, confidence=0.6))
        elif cat == "permission":
            packet.permission_candidates.append(m.body)
        elif cat == "question":
            packet.open_questions.append(m.body)
        # note → 후보 아님(버림). 회의 요약은 작업이 아니다.
    return packet


def approve_action_candidate(cand: ActionCandidate, *, room_id: str, proposed_by: str,
                             store_root: str) -> CommandProposal:
    """승인된 작업 후보 → CommandProposal(배정 포함). 여기서 Assignment Routing/Workspace로 연결.
    **회의 요약은 작업이 아니다 — 승인된 후보만 작업이 된다.**"""
    scope = cand.scope or {}
    repo = scope.get("repo")
    if isinstance(repo, str) and repo.startswith("repo."):
        repo = repo[len("repo."):]
    assignment = None
    if cand.suggested_role or repo or scope.get("workspace_ref"):
        assignment = AssignmentSpec(role=cand.suggested_role, repo=repo,
                                    workspace_ref=scope.get("workspace_ref"),
                                    provider=cand.suggested_provider)
    return proposals.propose_command(
        room_id=room_id, intent=cand.intent, provider=cand.suggested_provider,
        workspace_root="", proposed_by=proposed_by, store_root=store_root,
        acceptance=cand.acceptance, assignment=assignment)


def approve_decision_candidate(cand: DecisionCandidate, *, store_root: str, decided_by: str) -> Event:
    """승인된 결정 → DecisionRecord(event log). 코드 변경이 아니라 조직 결정 기록."""
    return EventLog(store_root).append(Event(
        event_type="decision.recorded", producer=decided_by, message=cand.statement,
        payload={"candidate_id": cand.candidate_id}))
