"""Coordinator (head agent) — propose-only 분해/라우팅 reasoning.

3관점 합의(2026-06-03 Vault decision): host 상주 head 프로세스는 죽인 pm_loop의 부활이라 금지.
대신 head = **worker 평면의 propose-only reasoner**:
- LLM 호출은 *주입*(worker가 BYOK로 실행) — Core는 키 0, 인터페이스 + propose-only 계약만 소유.
- 출력 = ActionCandidate[](close_meeting 후보와 동형). enqueue/confirm 절대 안 함(사람/정책 게이트 유지).
- classify_message(규칙기반 v0)의 LLM 대체 seam — 한 아이디어를 여러 task로 분해(규칙기반은 1메시지=1후보).
- 환각 방지: 후보는 source_message_ids로 출처 추적, 검증/승인은 사람.
"""
from __future__ import annotations

from app.nat.contracts import Message


def _msgs(*bodies):
    return [Message(room_id="r", sender={"type": "human", "id": "user://pm"}, body=b) for b in bodies]


def test_coordinator_decomposes_idea_into_multiple_candidates():
    """한 아이디어 → 여러 작업 후보(규칙기반 v0는 1메시지=1후보, LLM head는 분해)."""
    from app.nat.core.coordinator import decompose

    def fake_llm(transcript):
        return [
            {"intent": "TEAM_ONBOARDING.md 섹션 작성", "role": "frontend", "provider": "claude", "repo": "web"},
            {"intent": "support_levels.py 작성", "role": "backend", "provider": "codex", "repo": "api"},
        ]

    cands = decompose(_msgs("팀 온보딩 흐름을 개선하자"), llm=fake_llm)
    assert len(cands) == 2
    assert cands[0].intent.startswith("TEAM_ONBOARDING")
    assert cands[0].suggested_role == "frontend" and cands[0].suggested_provider == "claude"
    assert cands[0].scope.get("repo") == "web"
    assert all(c.state == "candidate" for c in cands)        # 후보 — 실행 아님
    assert cands[0].source_message_ids                       # 출처 추적(환각 방지)


def test_coordinator_corrects_unknown_role_and_provider():
    """LLM이 모르는 role/provider를 내면 안전 기본으로 정정(거짓 라우팅 방지)."""
    from app.nat.core.coordinator import decompose
    cands = decompose(_msgs("뭔가 하자"), llm=lambda t: [{"intent": "x", "role": "wizard", "provider": "gpt5"}])
    assert cands[0].suggested_role is None                   # 모르는 role → None(사람이 확정)
    assert cands[0].suggested_provider == "claude"           # 모르는 provider → 안전 기본


def test_coordinator_drops_empty_or_malformed():
    from app.nat.core.coordinator import decompose
    cands = decompose(_msgs("x"), llm=lambda t: [{"intent": ""}, {"role": "qa"}, "not-a-dict", {"intent": "real task"}])
    assert len(cands) == 1 and cands[0].intent == "real task"


def test_coordinator_is_propose_only_no_enqueue():
    """propose-only 계약: decompose는 queue/conductor를 받지 않는다 — 구조적으로 enqueue/confirm 불가."""
    import inspect
    from app.nat.core import coordinator
    params = set(inspect.signature(coordinator.decompose).parameters)
    assert "queue" not in params and "conductor" not in params and "confirm" not in params
    assert params == {"messages", "llm"}                     # 입력=회의+주입LLM, 출력=후보뿐


def test_coordinator_llm_is_injected_core_calls_no_provider():
    """Core는 provider를 직접 실행하지 않는다 — LLM은 주입(worker가 BYOK로 실행). 주입 함수만 호출됨."""
    from app.nat.core.coordinator import decompose
    called = {"n": 0, "saw_idea": False}

    def fake_llm(transcript):
        called["n"] += 1
        called["saw_idea"] = "온보딩" in transcript          # 회의 내용이 LLM에 전달됨
        return [{"intent": "task"}]

    decompose(_msgs("온보딩 개선"), llm=fake_llm)
    assert called["n"] == 1 and called["saw_idea"]           # 주입 LLM이 유일한 LLM 경로


def test_coordinator_candidates_feed_human_approval_not_auto_confirm(tmp_path):
    """head 출력은 close_meeting 후보와 동형 → approve_action_candidate로 사람이 승격(자동 confirm 아님)."""
    from app.nat.core.coordinator import decompose
    from app.nat.core.meeting import approve_action_candidate
    cands = decompose(_msgs("로그인 기능 출시하자"),
                      llm=lambda t: [{"intent": "로그인 UI 구현", "role": "frontend", "provider": "claude", "repo": "web"}])
    proposal = approve_action_candidate(cands[0], room_id="r", proposed_by="user://pm", store_root=str(tmp_path))
    assert proposal.assignment.role == "frontend"            # 후보 → 제안(배정 포함)
    assert proposal.state == "proposed"                      # confirm 전 — 실행 0(사람 게이트 유지)


# ──────────────── worker-path 실 배선: 진짜 LLM 출력 파싱 ────────────────
def test_decompose_prompt_demands_json_and_forbids_files():
    """worker가 LLM에 줄 프롬프트: JSON만 요구 + 파일 생성/수정 금지(분해는 reasoning, side-effect 0)."""
    from app.nat.core.coordinator import decompose_prompt
    p = decompose_prompt("- 온보딩 개선하자").lower()
    assert "json" in p
    assert "intent" in p and "role" in p
    assert "file" in p                                       # 파일 만들지 말라는 지시 포함


def test_parse_llm_plan_extracts_fenced_json():
    """진짜 claude/codex는 종종 ```json 펜스로 감싼다 — 추출해야 한다."""
    from app.nat.core.coordinator import parse_llm_plan
    text = '여기 계획입니다:\n```json\n[{"intent":"a","role":"frontend"}]\n```\n끝.'
    plan = parse_llm_plan(text)
    assert plan == [{"intent": "a", "role": "frontend"}]


def test_parse_llm_plan_bare_array():
    from app.nat.core.coordinator import parse_llm_plan
    assert parse_llm_plan('[{"intent":"x"}, {"intent":"y"}]') == [{"intent": "x"}, {"intent": "y"}]


def test_parse_llm_plan_garbage_returns_empty():
    """파싱 실패는 [](크래시 금지) — 후보 0이면 사람이 수동 분해."""
    from app.nat.core.coordinator import parse_llm_plan
    assert parse_llm_plan("죄송해요 잘 모르겠어요") == []
    assert parse_llm_plan("") == []
    assert parse_llm_plan('{"not": "a list"}') == []


def test_real_provider_output_flows_to_candidates():
    """worker-path 시뮬: 진짜 LLM 출력(텍스트) → parse → decompose → ActionCandidate[](propose-only)."""
    from app.nat.core.coordinator import decompose, parse_llm_plan
    fake_provider_stdout = 'Plan:\n```json\n[{"intent":"로그인 UI","role":"frontend","provider":"claude","repo":"web"}]\n```'
    plan = parse_llm_plan(fake_provider_stdout)
    cands = decompose(_msgs("로그인 기능 출시하자"), llm=lambda _t: plan)
    assert len(cands) == 1 and cands[0].suggested_role == "frontend" and cands[0].scope["repo"] == "web"
