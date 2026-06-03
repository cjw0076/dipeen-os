"""Meeting Closure Packet (4단계) — 회의방 메시지를 decision/task/permission/memory/question으로 분류.

**회의 요약은 작업이 아니다.** close_meeting은 *후보*만 만들고, 승인된 것만 실행 객체가 된다.
핵심 연결: action candidate 승인 → CommandProposal(배정 포함) → Assignment Routing → Workspace → worker.
"""
import pytest

from app.nat.contracts import ActionCandidate, Message, SenderRef
from app.nat.core.meeting import (approve_action_candidate, classify_message, close_meeting)


def _msg(body, mtype="discussion.message"):
    return Message(room_id="goal-1", sender=SenderRef(type="human", id="user://pm"),
                   message_type=mtype, body=body)


def test_plain_discussion_is_not_a_task():
    p = close_meeting("goal-1", [_msg("좋은 아침입니다. 회의 시작하죠")])
    assert p.task_candidates == []                  # discussion message ≠ task


def test_build_intent_becomes_action_candidate():
    p = close_meeting("goal-1", [_msg("로그인 UI 구현해줘")])
    assert len(p.task_candidates) == 1
    assert "로그인" in p.task_candidates[0].intent
    assert p.task_candidates[0].state == "candidate"   # 후보일 뿐(아직 작업 아님)


def test_decision_marker_becomes_decision():
    p = close_meeting("goal-1", [_msg("상태관리는 Zustand 쓰자")])
    assert len(p.decisions) == 1 and p.task_candidates == []


def test_memory_marker_becomes_memory_candidate():
    p = close_meeting("goal-1", [_msg("이 결정은 기억해두자")])
    assert len(p.memory_candidates) == 1


def test_question_becomes_open_question():
    p = close_meeting("goal-1", [_msg("테스트 실패 원인이 뭐야?")])
    assert len(p.open_questions) == 1


def test_permission_ask_becomes_permission_candidate():
    p = close_meeting("goal-1", [_msg("PR 만들어도 돼?")])
    assert len(p.permission_candidates) == 1 and p.task_candidates == []


def test_command_proposal_message_is_task_candidate():
    p = close_meeting("goal-1", [_msg("로그인 구현", "command.proposal")])
    assert len(p.task_candidates) == 1              # typed proposal → 바로 task 후보


def test_classify_precedence_build_over_decision():
    assert classify_message("로그인 구현하자") == "task"     # build verb가 decision marker보다 우선
    assert classify_message("Zustand 쓰자") == "decision"


@pytest.mark.asyncio
async def test_approve_action_candidate_creates_proposal_with_assignment(tmp_path):
    # ★ 핵심 연결: 승인된 action candidate → CommandProposal(배정) → Assignment Routing
    store = str(tmp_path / "nat")
    cand = ActionCandidate(title="login UI", intent="로그인 UI 구현",
                           suggested_role="frontend", suggested_provider="claude",
                           scope={"repo": "ezmap-web", "workspace_ref": "workspace://ezmap-web"})
    proposal = approve_action_candidate(cand, room_id="goal-1", proposed_by="user://web", store_root=store)
    assert proposal.intent == "로그인 UI 구현"
    assert proposal.assignment is not None
    assert proposal.assignment.role == "frontend"
    assert proposal.assignment.repo == "ezmap-web"
    assert proposal.assignment.workspace_ref == "workspace://ezmap-web"
