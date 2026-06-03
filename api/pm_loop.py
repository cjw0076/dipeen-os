"""
pm_loop.py -- PM Agent Loop (G 버전: 회의 모드 + 능동 완료 감지)

흐름:
  1. 사용자 채팅 수신
  2. [회의 모드] 팀 역량 파악 → 방향 논의 → 구조화된 계획 제안 → 확인 요청
  3. 사용자 확인 → Brief 생성 & 채팅 공유 → 태스크 배정
  4. task_update 이벤트 수신 → 배치 완료 시 자동 결과 보고
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
import websockets

API_URL        = os.getenv("API_URL", "http://localhost:8000")
WS_URL         = os.getenv("WS_URL",  "ws://localhost:8000")
TOKEN          = os.getenv("DIPEEN_API_TOKEN", "")
MODEL          = os.getenv("PM_MODEL", "claude-sonnet-4-6")
PM_AGENT_ID    = os.getenv("PM_AGENT_ID", "pm-agent")
SHARED_DIR     = os.getenv("DIPEEN_SHARED_DIR", str(
    __import__("pathlib").Path(__file__).parent.parent / "dipeen-shared"
))

# ── P3: PM 런타임 설정 ────────────────────────────────────────────
_PM_RUNTIME: dict = {
    "response_style": "detailed",  # "concise" | "detailed"
    "auto_execute": False,
    "skip_review": False,          # OPT-2: SPEAK/PASS 리뷰 스킵
}

# ── 상태 관리 (in-memory) ─────────────────────────────────────────

# 방별 회의 상태: room_id → { pending_plan, history }
ROOM_STATE: dict[str, dict] = {}

# 태스크 배치 추적: task_id → { room_id, subject, batch_id }
TASK_BATCH: dict[str, dict] = {}

# 배치 완료 감시: batch_id → { room_id, title, total, done, errors, results }
BATCH_STATE: dict[str, dict] = {}

# 태스크 봉투(wrap 계약): task_id → TaskEnvelope. 배정 시점에 결정 카드가 고정한
# scope_claims를 보관했다가, 보고 수신 시 Gatekeeper(출구 게이트)가 강제한다.
# (docs/dipeen-wrap-principle.md — 경계는 HQ, truth는 runner에 두지 않는다.)
TASK_ENVELOPE: dict = {}

# remediation 체인 추적: trace_id → { attempt, prev_reason }. 진전 단조성 가드용.
REMEDIATION_STATE: dict = {}

# 회의 단계 추적: room_id → { phase, turns, brief, last_activity }
# phase: DISCUSSING | SOLICITING | BRIEF_READY | EXECUTING | DONE
MEETING_STATE: dict[str, dict] = {}

# per-room 응답 락 (중복 응답 방지)
_ROOM_LOCKS: dict[str, asyncio.Lock] = {}

def _room_lock(room_id: str) -> asyncio.Lock:
    if room_id not in _ROOM_LOCKS:
        _ROOM_LOCKS[room_id] = asyncio.Lock()
    return _ROOM_LOCKS[room_id]


# ── 라우팅: 어떤 메시지에 응답할지 결정 ──────────────────────────────

def _should_respond(text: str, room_id: str) -> bool:
    """X-2: PM이 이 메시지에 응답해야 하는지 판단.

    응답 조건 (OR):
    1. @pm 멘션
    2. /task 커맨드
    3. Meeting이 SOLICITING / BRIEF_READY / EXECUTING 등 진행 중인 단계
    4. turns > 0 (대화가 이미 시작된 방)

    무시 조건:
    - 멘션 없음 + turns=0 → PM은 불려야 대답한다
    - 2글자 이하 단순 인사
    """
    t = text.strip()
    if len(t) <= 2:
        return False

    # 명시적 트리거
    if "@pm" in t.lower():
        return True
    if t.startswith("/task"):
        return True

    ms = _get_ms(room_id)
    phase = ms.get("phase", "DISCUSSING")
    turns = ms.get("turns", 0)

    # 진행 중인 meeting
    if phase in ("SOLICITING", "BRIEF_READY", "EXECUTING"):
        return True

    # 대화가 이미 시작됨 → 의도 분류 후 처리
    if turns > 0:
        return True

    # 그 외: PM은 불려야 대답한다 (멘션 없으면 무시)
    return False


# ── 확인 감지 ─────────────────────────────────────────────────────

_CONFIRM_KEYWORDS = {
    "시작", "진행", "ok", "오케이", "좋아", "맞아", "그렇게", "ㅇㅇ",
    "응", "예", "yes", "go", "고", "해줘", "해줘요", "부탁해", "부탁합니다",
    "진행해", "진행해줘", "시작해", "시작해줘", "ㅇ", "그래",
}

def _is_confirmation(text: str) -> bool:
    t = text.strip().lower()
    return any(kw in t for kw in _CONFIRM_KEYWORDS) and len(t) < 30


# ── 회의 상태 헬퍼 ───────────────────────────────────────────────

def _get_ms(room_id: str) -> dict:
    """room별 회의 상태 반환 (없으면 초기화)."""
    return MEETING_STATE.setdefault(room_id, {
        "phase": "DISCUSSING",
        "mode": "plan",   # "plan" | "brainstorm"
        "turns": 0,
        "brief": None,
        "last_activity": datetime.now(timezone.utc).isoformat(),
    })


async def _broadcast_event(event: dict, client: httpx.AsyncClient) -> None:
    """pm_loop → API /api/meeting/broadcast → WS 클라이언트에게 전파."""
    try:
        await client.post(
            f"{API_URL}/api/meeting/broadcast",
            json={"event": event},
            headers=_auth_headers(),
            timeout=5,
        )
    except Exception as e:
        print(f"[PM] broadcast 실패: {e}", file=sys.stderr)


async def _set_phase(room_id: str, phase: str, client: httpx.AsyncClient,
                     brief: dict | None = None) -> None:
    """회의 단계 전환 + WS 브로드캐스트 + API 상태 동기화."""
    ms = _get_ms(room_id)
    ms["phase"] = phase
    ms["last_activity"] = datetime.now(timezone.utc).isoformat()
    if brief is not None:
        ms["brief"] = brief

    await _broadcast_event({
        "type": "meeting_phase",
        "room_id": room_id,
        "phase": phase,
        "brief": ms.get("brief"),
    }, client)

    # WS 재연결 복구용 상태 동기화
    try:
        await client.post(
            f"{API_URL}/api/meeting/state",
            json={"room_id": room_id, "phase": phase, "brief": ms.get("brief"), "participants": []},
            headers=_auth_headers(),
            timeout=5,
        )
    except Exception:
        pass


async def _solicit_and_finalize(room_id: str, plan: dict, client: httpx.AsyncClient) -> None:
    """SOLICITING(팀 역량 확인 + SPEAK/PASS 검토) → BRIEF_READY(브리프 공개) 전환."""
    await _set_phase(room_id, "SOLICITING", client)

    # OPT-2: SPEAK/PASS 스킵 (설정 또는 에이전트 1명 이하)
    concerns = ""
    roster = await _get_roster(client)
    online_count = len([a for a in roster if a.get("status") != "offline"])

    if _PM_RUNTIME.get("skip_review") or online_count <= 1:
        print(f"[PM] SPEAK/PASS 스킵 (skip_review={_PM_RUNTIME.get('skip_review')}, online={online_count})", flush=True)
    else:
        await _broadcast_event({
            "type": "agent_input_request",
            "room_id": room_id,
            "question": "이 계획에 대한 의견을 주세요.",
            "context_summary": plan.get("title", ""),
        }, client)
        await _send_chat(room_id, "📋 팀 역량을 확인하고 에이전트 검토를 수행합니다...", client)
        try:
            concerns = await _agent_review(plan, roster, room_id, client)
        except Exception as e:
            print(f"[PM] agent review 오류: {e}", file=sys.stderr)

    brief_text = plan.get("brief", "")
    if concerns:
        brief_text = f"{brief_text}\n\n## 에이전트 검토 의견\n{concerns}"

    brief_data = {
        "title": plan.get("title", ""),
        "brief": brief_text,
        "tasks": plan.get("tasks", []),
    }
    await _set_phase(room_id, "BRIEF_READY", client, brief=brief_data)


# ── 프롬프트 ──────────────────────────────────────────────────────

BRAINSTORM_PROMPT = """\
당신은 dipeen PM(프로젝트 매니저) 에이전트입니다.
현재 모드: **브레인스토밍** -- 자유로운 아이디어 발산 단계입니다.

지시사항:
1. 판단을 보류하고 창의적 아이디어를 발산하세요. 현실성보다 가능성 우선
2. 다양한 관점(기술/UX/비즈니스)에서 아이디어를 제안하세요
3. 사용자의 아이디어를 발전시키고, 연결하고, 발전시키세요
4. 계획이나 태스크를 구조화하지 마세요 -- 오직 아이디어 목록만
5. 탐색적 언어 사용: "이건 어떨까요?", "다른 각도로 보면...", "흥미로운 가능성은..."
6. 완벽하지 않아도 됩니다. 아이디어의 양이 질보다 중요한 단계

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{
  "reply": "자유로운 아이디어 제안 (마크다운 허용, 불릿 리스트와 이모지 적극 활용)"
}
"""

DISCUSS_PROMPT = """\
당신은 dipeen PM(프로젝트 매니저) 에이전트입니다.
현재 모드: **회의 모드** -- 사용자 및 팀과 프로젝트 방향을 논의합니다.

지시사항:
1. 사용자의 요청을 이해하고, 빠진 정보가 있으면 간결하게 질문할 것
2. 구현 방향을 제안할 때는 팀 역량(roster)을 반영할 것
3. 계획이 정해지면 구조화된 brief를 포함한 제안을 만들고 "진행할까요?" 확인을 요청할 것
4. 아직 태스크를 생성하지 말 것 -- 사용자 확인 후에만 생성
5. 이미 최근에 완료된 작업이 있으면 연속성을 유지할 것
6. 태스크 간 의존성은 각 태스크의 로컬 "id"로 표현할 것:
   - 각 태스크에 계획 내부에서 고유한 "id"를 부여 (예: "t1", "t2", ...)
   - Wave 1 (병렬 실행 가능): "blocked_by": null
   - Wave 2 (Wave 1 완료 후): "blocked_by"에 선행 태스크의 "id"를 지정 (예: "t1")
   - 실제 서버 task_id("T-...")는 시스템이 생성하므로 절대 직접 쓰지 말 것
   - 독립적인 태스크는 "blocked_by": null로 병렬 실행 최대화

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{
  "reply": "사용자에게 보낼 메시지 (마크다운 허용, 2-4문장 또는 짧은 계획)",
  "proposed_plan": {
    "title": "프로젝트/기능 제목",
    "brief": "## 목표\\n...\\n\\n## 결정사항\\n- ...\\n\\n## 작업 목록\\n- [ ] ...",
    "tasks": [
      {
        "id": "t1",
        "subject": "태스크 제목 (50자 이내)",
        "task": "원자적이고 구체적인 1문장 목표",
        "expected_outcome": "성공 기준을 포함한 구체적 산출물 (예: Button.tsx에 hover 스타일 추가, 기존 테스트 통과)",
        "required_tools": ["Bash", "Edit", "Read"],
        "must_do": ["기존 테스트 모두 통과", "TypeScript strict 모드 준수"],
        "must_not_do": ["다른 컴포넌트 수정 금지", "패키지 추가 금지"],
        "context": "관련 파일: src/Button.tsx:42, 패턴: shadcn/ui 기준. 에이전트는 완료 후 .dipeen-result.json의 subtasks 배열에 후속 작업(QA 검증, 문서 업데이트 등)을 추가할 수 있음: [{\"subject\": \"...\", \"prompt\": \"...\", \"to_role\": \"QA\"}]",
        "required_role": "FE" | "BE" | "QA" | null,
        "required_persona": "coder" | "planner" | "researcher" | "reviewer" | "marketer",
        "required_skills": ["React"],
        "blocked_by": null,
        "complexity": "quick" | "normal" | "deep"
      }
    ]
  }
}

proposed_plan이 아직 확정되지 않았으면 null로 설정. 질문이 필요한 경우도 null.
"""

REVIEW_PROMPT = """\
당신은 dipeen PM(프로젝트 매니저) 에이전트입니다.
현재 모드: **코드 리뷰** -- 코드 품질·보안·설계를 검토합니다.

지시사항:
1. 사용자가 제공한 코드, diff, 또는 PR 내용을 분석하세요
2. 버그, 보안 취약점, 성능 이슈, 설계 문제를 항목별로 지적하세요
3. 각 이슈에 심각도(🔴 critical / 🟡 warning / 🟢 suggestion)를 표시하세요
4. 수정 방법을 구체적으로 제안하세요 (코드 스니펫 포함 가능)
5. 리뷰 태스크를 팀에 배정할 수 있으면 proposed_plan에 포함하세요

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{
  "reply": "리뷰 결과 (마크다운, 심각도별 이슈 목록)",
  "proposed_plan": {
    "title": "코드 리뷰: {대상}",
    "brief": "## 리뷰 요약\\n...\\n\\n## 주요 이슈\\n- ...\\n\\n## 개선 방향\\n- ...",
    "tasks": [
      {
        "subject": "수정 태스크 제목",
        "prompt": "구체적인 수정 지시",
        "required_role": "FE" | "BE" | "QA" | null,
        "required_persona": "reviewer" | "coder",
        "required_skills": [],
        "blocked_by": null
      }
    ]
  }
}

리뷰 태스크가 없으면 proposed_plan을 null로 설정.
"""

DEBATE_PROMPT = """\
당신은 dipeen PM(프로젝트 매니저) 에이전트입니다.
현재 모드: **아키텍처 토론 (ADR)** -- 기술적 의사결정을 구조화합니다.

지시사항:
1. 제안된 아키텍처/설계/기술 선택을 중립적으로 분석하세요
2. 찬성 근거(pros)와 반대 근거(cons)를 균형 있게 제시하세요
3. 대안(alternatives)을 2-3가지 제안하세요
4. 최종 권고사항을 제시하고 ADR 형식으로 정리하세요
5. 합의가 됐으면 결정 사항을 태스크로 전환할 수 있습니다

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{
  "reply": "ADR 형식 분석 (마크다운):\\n## 상황\\n...\\n## 결정\\n...\\n## 근거\\n### 찬성\\n- ...\\n### 반대\\n- ...\\n## 대안\\n- ...\\n## 결론\\n...",
  "proposed_plan": {
    "title": "ADR: {결정 제목}",
    "brief": "## 배경\\n...\\n\\n## 결정 사항\\n...\\n\\n## 후속 작업\\n- ...",
    "tasks": [
      {
        "subject": "ADR 구현 태스크",
        "prompt": "결정된 아키텍처 구현 지시",
        "required_role": null,
        "required_persona": "planner",
        "required_skills": [],
        "blocked_by": null
      }
    ]
  }
}

토론이 진행 중이면 proposed_plan을 null로 설정.
"""

DISPATCH_PROMPT = """\
당신은 dipeen PM 에이전트입니다.
사용자가 계획을 확인했습니다. 확정된 계획과 팀 현황을 바탕으로 태스크를 생성하고 최적 에이전트에 배정하세요.

배정 원칙:
1. required_role/required_skills가 일치하는 에이전트 우선
2. status가 "idle"이고 available=true인 에이전트만 고려
3. competency 점수가 높은 에이전트 우선
4. 비용 절감: ollama/gemini 에이전트가 있으면 단순 태스크는 이쪽으로 우선 배정
5. 현재 팀에 없는 역할이 필요하면 required_role만 명시하고 배정은 시스템에 위임

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{
  "reply": "작업 배정 완료 메시지 (한국어, 1-2문장, 어떤 에이전트에게 배정했는지 포함)",
  "tasks": [
    {
      "id": "t1",
      "subject": "태스크 제목 (50자 이내)",
      "prompt": "구체적인 구현 지시",
      "required_role": "FE" | "BE" | "QA" | null,
      "required_persona": "coder" | "planner" | "researcher" | "reviewer" | "marketer",
      "required_skills": ["React"],
      "blocked_by": null
    }
  ]
}

의존성은 각 태스크의 로컬 "id"로 표현하세요. 선행 태스크가 있으면 "blocked_by"에
그 태스크의 "id"(예: "t1")를 지정하고, 실제 서버 task_id("T-...")는 직접 쓰지 마세요.
"""

AGENT_REVIEW_PROMPT = """\
당신은 {name}({role}) 에이전트입니다.
담당 skills: {skills}

PM이 제안한 계획을 아래에서 검토하고 SPEAK 또는 PASS로 응답하세요.

[제안된 계획]
{plan_summary}

[이미 나온 우려 사항]
{prior_concerns}

판단 기준:
- 내 역할/전문 영역에서 리스크, 빠진 요소, 개선점이 보이면 → SPEAK
- 계획이 충분히 잘 구성되어 있거나 내 전문 영역 밖이면 → PASS
- 이미 나온 우려와 동일한 내용이면 → PASS

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{{"decision": "SPEAK", "concern": "한 줄 우려 또는 제안 (50자 이내)"}}
또는
{{"decision": "PASS"}}
"""


# ── X-1: 의도 분류 프롬프트 ──────────────────────────────────────────

INTENT_CLASSIFY_PROMPT = """\
사용자 메시지의 의도를 분류하세요.

- work: 코드 작성, 기능 구현, 버그 수정, UI 변경, 배포, 리팩토링 등 실제 개발 작업 요청
- question: 기술 질문, 상태 확인, 정보 요청, "왜?", "어떻게?" 등 (태스크 불필요)
- casual: 인사, 잡담, 감정 표현, 일상 대화 (간단 반응 또는 무시)
- confirm: 계획 승인, 시작 지시 (ok, 진행해, 시작해, 좋아)

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{"intent": "work" | "question" | "casual" | "confirm"}
"""

QUESTION_PROMPT = """\
당신은 dipeen PM 에이전트입니다.
사용자가 질문을 했습니다. 간결하게 답변하세요.
태스크를 만들지 마세요 — 질문에만 답하세요.

팀 현황:
{roster}

반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{"reply": "간결한 답변 (2-3문장 이내)"}
"""

CASUAL_PROMPT = """\
사용자가 가벼운 말을 했습니다. 친근하게 1줄로 반응하세요.
반드시 아래 JSON 형식으로만 응답하세요 (markdown 코드블록 없이):
{"reply": "짧은 반응 (1줄, 이모지 허용)"}
"""


# ── 공통 헬퍼 ─────────────────────────────────────────────────────

def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


async def _get_roster(client: httpx.AsyncClient) -> list[dict]:
    try:
        r = await client.get(f"{API_URL}/api/agents/roster", headers=_auth_headers(), timeout=5)
        return r.json().get("agents", [])
    except Exception as e:
        print(f"[PM] roster 조회 실패: {e}", file=sys.stderr)
        return []


def _format_roster(agents: list[dict]) -> str:
    if not agents:
        return "팀 정보 없음"
    lines = []
    for a in agents:
        status = "[OK] 가용" if a.get("available") else "🔴 작업중"
        skills = ", ".join(a.get("skills", [])[:5]) or "미설정"
        personas = ", ".join(a.get("personas", [])) or "coder"
        comp = a.get("competency", {})
        role = (a.get("role") or "").upper()
        score = comp.get(role, 0)
        lines.append(
            f"- {a['agent_id']} ({role}/{a.get('llm_provider','?')}) {status} | "
            f"스킬: {skills} | 페르소나: {personas} | 숙련도: {score}/100"
        )
    return "\n".join(lines)


async def _get_recent_artifacts(client: httpx.AsyncClient, limit: int = 3) -> str:
    """Result Distillation: 최근 완료 태스크의 artifacts 요약."""
    try:
        r = await client.get(
            f"{API_URL}/api/tasks",
            params={"status": "done"},
            headers=_auth_headers(),
            timeout=5,
        )
        tasks = r.json()[:limit]
    except Exception:
        return ""

    lines = []
    for t in tasks:
        arts = (t.get("result") or {}).get("artifacts") or {}
        if not arts:
            continue
        files = ", ".join(arts.get("changed_files", [])[:3]) or "없음"
        decisions = " / ".join(arts.get("key_decisions", [])[:2])
        blockers = " / ".join(arts.get("blockers", [])[:2])
        line = f"- [{t['task_id']}] {t['subject']}: 변경={files}"
        if decisions:
            line += f" | 결정={decisions}"
        if blockers:
            line += f" | 미완={blockers}"
        lines.append(line)
    return "\n".join(lines) if lines else ""


async def _send_chat(room_id: str, text: str, client: httpx.AsyncClient,
                     sender: str | None = None) -> None:
    try:
        await client.post(
            f"{API_URL}/api/chat/messages",
            json={
                "room_id": room_id,
                "sender": sender or PM_AGENT_ID,
                "sender_type": "pm",
                "text": text,
            },
            headers=_auth_headers(),
            timeout=5,
        )
    except Exception as e:
        print(f"[PM] 채팅 전송 실패: {e}", file=sys.stderr)


async def _agent_review(plan: dict, roster: list[dict], room_id: str, client: httpx.AsyncClient) -> str:
    """SPEAK/PASS 프로토콜: 온라인 에이전트 관점에서 계획을 검토하고 우려 사항을 수집한다."""
    online_agents = [a for a in roster if a.get("status") != "offline"]
    if not online_agents:
        return ""

    plan_summary = (
        f"제목: {plan.get('title', '')}\n"
        f"개요: {plan.get('brief', '')}\n"
        f"태스크 수: {len(plan.get('tasks', []))}"
    )

    concerns: list[str] = []
    for agent in online_agents:
        name = agent.get("agent_id", "agent")
        role = agent.get("role", "?")
        skills = ", ".join(agent.get("skills", [])) or "없음"
        prior = "\n".join(f"- {c}" for c in concerns) if concerns else "없음"

        prompt = AGENT_REVIEW_PROMPT.format(
            name=name, role=role, skills=skills,
            plan_summary=plan_summary, prior_concerns=prior,
        )
        try:
            result = await _call_llm_with_tokens(prompt, "", max_tokens=200, model=_HAIKU)
            decision = result.get("decision", "PASS").upper()
            if decision == "SPEAK":
                concern = result.get("concern", "").strip()
                if concern:
                    concerns.append(f"[{name}] {concern}")
                    await _send_chat(room_id, f"💬 [{name}] {concern}", client)
                    print(f"[PM] SPEAK: [{name}] {concern}", flush=True)
            else:
                print(f"[PM] PASS: [{name}]", flush=True)
        except Exception as e:
            print(f"[PM] agent review 실패 ({name}): {e}", file=sys.stderr)

    return "\n".join(concerns)


# ── J-5: Preemptive Compaction ───────────────────────────────────────────────
# 78% 토큰 사용 시 대화 히스토리 압축 (claw-code-main 패턴)

_MAX_HISTORY_TOKENS = 200_000
_COMPACT_THRESHOLD  = 0.78   # 78% 도달 시 compact
_COMPACT_KEEP_TURNS = 4      # compact 후 최신 N턴 유지


def _estimate_tokens(history: list[dict]) -> int:
    """대화 히스토리의 토큰 수 추정 (4자 = 1토큰 근사값)."""
    total_chars = sum(
        len(h.get("user", "")) + len(h.get("pm", ""))
        for h in history
    )
    return total_chars // 4


def _compact_history(history: list[dict]) -> list[dict]:
    """
    히스토리 압축: 오래된 턴 요약 → 최신 N턴만 유지.
    요약은 히스토리 첫 항목의 'pm' 필드에 삽입.
    """
    if len(history) <= _COMPACT_KEEP_TURNS:
        return history

    old = history[:-_COMPACT_KEEP_TURNS]
    recent = history[-_COMPACT_KEEP_TURNS:]

    # 오래된 대화 요약 (간단한 텍스트 요약)
    summary_lines = ["[이전 대화 요약]"]
    for h in old:
        user_snippet = h.get("user", "")[:80]
        pm_snippet = h.get("pm", "")[:80]
        summary_lines.append(f"- 사용자: {user_snippet}...")
        summary_lines.append(f"  PM: {pm_snippet}...")

    summary_entry = {
        "user": "[이전 대화 압축됨]",
        "pm": "\n".join(summary_lines),
    }
    return [summary_entry] + recent


def _maybe_compact_history(state: dict, room_id: str = "general") -> None:
    """J-5-3: 히스토리 토큰 임계값 초과 시 compact + 컨텍스트 재주입."""
    history = state.get("history", [])
    if not history:
        return
    estimated = _estimate_tokens(history)
    threshold = int(_MAX_HISTORY_TOKENS * _COMPACT_THRESHOLD)
    if estimated > threshold:
        print(f"[PM] 히스토리 compact: {estimated} > {threshold} tokens", flush=True)
        compacted = _compact_history(history)

        # J-5-3: WORKSPACE.md + 현재 배치 상태를 compact 요약에 재주입
        context_parts = []
        try:
            ws_path = _workspace_path(room_id)
            if ws_path.exists():
                ws_content = ws_path.read_text(encoding="utf-8")
                # Current Sprint 섹션만 추출
                if "## Current Sprint" in ws_content:
                    sprint = ws_content.split("## Current Sprint")[1].split("## ")[0].strip()
                    if sprint:
                        context_parts.append(f"[현재 스프린트] {sprint[:200]}")
        except Exception:
            pass

        # 진행 중인 배치 상태
        active_batches = [
            f"{v['title']} ({v['done']}/{v['total']})"
            for v in BATCH_STATE.values()
            if v.get("done", 0) < v.get("total", 0)
        ]
        if active_batches:
            context_parts.append(f"[진행 중인 배치] {', '.join(active_batches)}")

        if context_parts and compacted:
            compacted[0]["pm"] += "\n\n" + "\n".join(context_parts)

        state["history"] = compacted


_HAIKU = "claude-haiku-4-5"  # OPT-1: 저비용 호출용

_USE_CLI = bool(os.getenv("PM_USE_CLI"))  # P-R: Claude Code CLI(구독) 사용 → API 크레딧 불필요


async def _call_claude_cli(system: str, user_content: str,
                           max_tokens: int = 2048, model: str | None = None) -> dict:
    """Claude 구독으로 호출 — API 크레딧 0 (원칙 #6).

    1순위: 구독 OAuth로 Messages API 직접 호출(subscription_llm) — 빠르고, `claude -p`
           빈출력 버그("Expecting value: line 1 column 1") 없음.
    2순위: `claude -p` subprocess (직접 호출 불가 시 fallback).
    """
    mdl = model or MODEL
    # ── 1순위: 구독 OAuth 직접 Messages API (크레딧 0, 안정 JSON) ──
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from app.subscription_llm import complete_json, available
        if available():
            return await asyncio.to_thread(
                complete_json, system, user_content,
                model=mdl, max_tokens=max_tokens, timeout=180,
            )
    except Exception as e:
        print(f"[PM] 구독 직접호출 실패 → CLI fallback: {e}", file=sys.stderr)
    # ── 2순위: `claude -p` subprocess (기존 경로) ──
    prompt = (system or "") + "\n\n" + (user_content or "응답하세요.") + (
        "\n\n[IMPORTANT: Output ONLY the raw JSON object described above. "
        "No prose, no markdown fences, no tools.]"
    )
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 죽은 키 제거 → 구독
    import shutil
    claude_bin = shutil.which("claude") or "claude"
    base = [claude_bin, "-p", "--output-format", "json"]   # 구조화 엔벨로프 → 안정 파싱(빈출력 방지)
    # Windows npm shim(claude.CMD)은 cmd /c 경유 + 프롬프트는 stdin으로(인자 따옴표 회피)
    argv = ["cmd", "/c", *base] if os.name == "nt" else base
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")), timeout=180
        )
    except asyncio.TimeoutError:
        proc.kill()
        print("[PM] CLI timeout(180s)", file=sys.stderr)
        return {}
    raw = (out or b"").decode("utf-8", "replace").strip()
    # --output-format json 엔벨로프({type:result, result:"<text>"})에서 실제 응답 추출
    text = raw
    try:
        env_obj = json.loads(raw)
        if isinstance(env_obj, dict) and "result" in env_obj:
            text = str(env_obj["result"]).strip()
    except Exception:
        pass
    if "```" in text:
        seg = text.split("```")
        text = seg[1] if len(seg) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    if not text:
        print(f"[PM] CLI 빈 출력. stderr={(err or b'').decode('utf-8','replace')[:200]}", file=sys.stderr)
        return {}
    return json.loads(text)


async def _call_llm_with_tokens(system: str, user_content: str, max_tokens: int = 2048,
                                 model: str | None = None) -> dict:
    """max_tokens + model을 조절 가능한 LLM 호출. model=None이면 기본 MODEL."""
    if _USE_CLI:
        try:
            return await _call_claude_cli(system, user_content, max_tokens=max_tokens, model=model)
        except Exception as e:
            print(f"[PM] CLI 호출 실패: {e}", file=sys.stderr)
            return {}
    try:
        import anthropic
        ac = anthropic.AsyncAnthropic()
        resp = await ac.messages.create(
            model=model or MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}] if user_content else [{"role": "user", "content": "응답하세요."}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"[PM] LLM 호출 실패: {e}", file=sys.stderr)
        return {}


# J-4-3: PM-Loop LLM Fallback Chain
_PM_FALLBACK_MODELS = [MODEL, "claude-sonnet-4-6", "claude-haiku-4-5"]
# 중복 제거 + 순서 유지
_PM_MODELS = list(dict.fromkeys(_PM_FALLBACK_MODELS))


async def _call_llm(system: str, user_content: str) -> dict:
    last_error = None

    # OPT-4: concise 모드일 때 max_tokens 줄이기
    style = _PM_RUNTIME.get("response_style", "detailed")
    max_tok = 800 if style == "concise" else 2048
    if style == "concise":
        system = system + "\n\n[중요: 2문장 이내로 간결하게 답변하세요.]"

    if _USE_CLI:
        try:
            return await _call_claude_cli(system, user_content, max_tokens=max_tok)
        except Exception as e:
            print(f"[PM] CLI 호출 실패: {e}", file=sys.stderr)
            return {"reply": "오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "proposed_plan": None}

    import anthropic
    ac = anthropic.AsyncAnthropic()
    for model in _PM_MODELS:
        try:
            resp = await ac.messages.create(
                model=model,
                max_tokens=max_tok,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            if model != _PM_MODELS[0]:
                print(f"[PM] fallback 모델 사용: {model}", flush=True)
            return result
        except anthropic.RateLimitError as e:
            print(f"[PM] 429 rate limit ({model}): {e} — fallback 시도", file=sys.stderr)
            last_error = e
            await asyncio.sleep(2)
        except anthropic.APIStatusError as e:
            print(f"[PM] API error ({model}, {e.status_code}): {e} — fallback 시도", file=sys.stderr)
            last_error = e
        except json.JSONDecodeError as e:
            print(f"[PM] JSON 파싱 실패 ({model}): {e}", file=sys.stderr)
            last_error = e
        except Exception as e:
            print(f"[PM] LLM 호출 실패 ({model}): {e}", file=sys.stderr)
            last_error = e

    print(f"[PM] 모든 모델 실패: {last_error}", file=sys.stderr)
    return {"reply": "오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "proposed_plan": None}


# ── 핵심 로직 ─────────────────────────────────────────────────────

async def _handle_brainstorm(text: str, room_id: str, state: dict,
                             client: httpx.AsyncClient) -> None:
    """브레인스토밍 모드: 자유로운 아이디어 발산, 구조화 없음."""
    history_text = ""
    if state.get("history"):
        lines = []
        for h in state["history"][-4:]:
            lines.append(f"사용자: {h['user']}")
            lines.append(f"PM: {h['pm']}")
        history_text = "이전 대화:\n" + "\n".join(lines) + "\n\n"

    context = f"{history_text}사용자: {text}"
    result = await _call_llm(BRAINSTORM_PROMPT, context)
    reply = result.get("reply", "")

    await _send_chat(room_id, reply, client)
    state.setdefault("history", []).append({"user": text, "pm": reply})
    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]


async def _handle_review(text: str, room_id: str, state: dict,
                         client: httpx.AsyncClient) -> None:
    """리뷰 모드: 코드/PR 분석 → 이슈 목록 → 선택적 수정 태스크 배정."""
    history_text = ""
    if state.get("history"):
        lines = []
        for h in state["history"][-4:]:
            lines.append(f"사용자: {h['user']}")
            lines.append(f"PM: {h['pm']}")
        history_text = "이전 대화:\n" + "\n".join(lines) + "\n\n"

    ms = _get_ms(room_id)
    context = f"{history_text}사용자 리뷰 요청: {text}"
    result = await _call_llm(REVIEW_PROMPT, context)
    reply = result.get("reply", "")
    await _send_chat(room_id, reply, client)

    state.setdefault("history", []).append({"user": text, "pm": reply})
    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]

    plan = result.get("proposed_plan")
    if plan and plan.get("tasks"):
        state["pending_plan"] = plan
        ms["phase"] = "BRIEF_READY"
        await _solicit_and_finalize(room_id, plan, client)


async def _handle_debate(text: str, room_id: str, state: dict,
                         client: httpx.AsyncClient) -> None:
    """토론 모드: 기술적 의사결정 → ADR 형식 분석 → 선택적 구현 태스크."""
    history_text = ""
    if state.get("history"):
        lines = []
        for h in state["history"][-4:]:
            lines.append(f"사용자: {h['user']}")
            lines.append(f"PM: {h['pm']}")
        history_text = "이전 대화:\n" + "\n".join(lines) + "\n\n"

    ms = _get_ms(room_id)
    context = f"{history_text}토론 주제: {text}"
    result = await _call_llm(DEBATE_PROMPT, context)
    reply = result.get("reply", "")
    await _send_chat(room_id, reply, client)

    state.setdefault("history", []).append({"user": text, "pm": reply})
    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]

    plan = result.get("proposed_plan")
    if plan and plan.get("tasks") and _is_confirmation(text):
        state["pending_plan"] = plan
        ms["phase"] = "BRIEF_READY"
        await _solicit_and_finalize(room_id, plan, client)


async def handle_user_message(text: str, room_id: str, client: httpx.AsyncClient) -> None:
    """회의 모드: 논의 → 계획 제안 → 확인 → 배정."""
    state = ROOM_STATE.setdefault(room_id, {"pending_plan": None, "history": []})
    _maybe_compact_history(state, room_id)  # J-5: 토큰 임계 초과 시 compact + 컨텍스트 재주입
    ms = _get_ms(room_id)
    ms["last_activity"] = datetime.now(timezone.utc).isoformat()

    print(f"[PM] 메시지 ({ms['phase']}, 턴={ms['turns']}): {text[:60]}", flush=True)

    # ── 모드별 분기 ──
    current_mode = ms.get("mode", "plan")
    if current_mode == "brainstorm":
        await _handle_brainstorm(text, room_id, state, client)
        return
    if current_mode == "review":
        await _handle_review(text, room_id, state, client)
        return
    if current_mode == "debate":
        await _handle_debate(text, room_id, state, client)
        return

    # ── X-3: /task 커맨드 → 강제 work intent ──
    if text.strip().startswith("/task"):
        task_text = text.strip()[5:].strip()
        if task_text:
            ms["turns"] = ms.get("turns", 0) + 1
            # /task FE 내용 → required_role 추출
            role_hint = None
            for r in ("FE", "BE", "QA"):
                if task_text.upper().startswith(r + " "):
                    role_hint = r
                    task_text = task_text[len(r):].strip()
                    break
            # 바로 태스크 생성
            roster = await _get_roster(client)
            context = f"팀 현황:\n{_format_roster(roster)}\n\n사용자 지시: {task_text}"
            result = await _call_llm(DISPATCH_PROMPT, context)
            tasks_def = result.get("tasks", [])
            if role_hint and tasks_def:
                for td in tasks_def:
                    td.setdefault("required_role", role_hint)
            plan = {"title": task_text[:50], "tasks": tasks_def, "brief": task_text}
            await _set_phase(room_id, "EXECUTING", client)
            await _dispatch_plan(plan, room_id, client)
            return

    # ── EXECUTING/DONE 중 메시지 ──
    if ms["phase"] in ("EXECUTING", "DONE") and not _is_confirmation(text):
        if ms["phase"] == "DONE":
            ms.update({"phase": "DISCUSSING", "turns": 0, "brief": None})
            state["pending_plan"] = None
            state["history"] = []
            await _set_phase(room_id, "DISCUSSING", client)
        else:
            # v1: EXECUTING 중에도 방을 얼리지 않는다 — 질문·상태에 대화로 응답하되,
            # 새 배치는 절대 시작하지 않는다(중첩 디스패치 방지).
            try:
                ans = await _call_llm(
                    "너는 dipeen PM-Agent다. 팀 작업이 지금 실행(EXECUTING) 중이다. 사용자 메시지에 "
                    "짧고 도움되게 답하라(진행 상황 안내/질문 응답). 절대 새 작업을 분배하거나 계획하지 마라. "
                    "새 작업 요청이면 '현재 배치 완료 후 반영하겠습니다'라고만 안내하라. "
                    'JSON {"reply": "..."} 형식으로만 답하라.',
                    f"진행 중 브리프: {ms.get('brief') or '(작업 진행 중)'}\n사용자: {text}",
                )
                reply = (ans or {}).get("reply") or "작업 진행 중입니다. 완료되면 바로 보고드리겠습니다."
            except Exception:
                reply = "작업 진행 중입니다. 완료되면 바로 보고드리겠습니다."
            await _send_chat(room_id, reply, client)
            return

    # ── 확인 응답 처리 (BRIEF_READY 단계에서만) ──
    if state["pending_plan"] and _is_confirmation(text) and ms["phase"] == "BRIEF_READY":
        await _set_phase(room_id, "EXECUTING", client)
        await _dispatch_plan(state["pending_plan"], room_id, client)
        state["pending_plan"] = None
        return

    # ── X-1: 의도 분류 (첫 메시지 또는 새 대화 시작 시) ──
    intent = "work"  # 기본값
    clean_text = text.replace("@pm", "").strip()

    if ms["turns"] == 0 or ms["phase"] == "DISCUSSING":
        # LLM으로 의도 분류 (저비용 호출)
        try:
            cls_result = await _call_llm_with_tokens(
                INTENT_CLASSIFY_PROMPT, f"사용자: {clean_text}", max_tokens=50, model=_HAIKU,
            )
            intent = cls_result.get("intent", "work")
            print(f"[PM] 의도 분류: {intent} ← \"{clean_text[:40]}\"", flush=True)
        except Exception:
            intent = "work"  # 분류 실패 시 work로 fallback

    # ── 의도별 분기 ──
    if intent == "casual":
        result = await _call_llm_with_tokens(CASUAL_PROMPT, f"사용자: {clean_text}", max_tokens=100, model=_HAIKU)
        reply = result.get("reply", "")
        if reply:
            await _send_chat(room_id, reply, client)
        return

    if intent == "question":
        roster = await _get_roster(client)
        q_prompt = QUESTION_PROMPT.format(roster=_format_roster(roster))
        result = await _call_llm_with_tokens(q_prompt, f"사용자 질문: {clean_text}", max_tokens=500, model=_HAIKU)
        reply = result.get("reply", "")
        if reply:
            await _send_chat(room_id, reply, client)
        return

    if intent == "confirm":
        # 기존 _is_confirmation 로직으로 위임
        if state["pending_plan"] and ms["phase"] == "BRIEF_READY":
            await _set_phase(room_id, "EXECUTING", client)
            await _dispatch_plan(state["pending_plan"], room_id, client)
            state["pending_plan"] = None
        return

    # intent == "work" → 기존 회의 모드 논의 진행
    ms["turns"] = ms.get("turns", 0) + 1
    roster = await _get_roster(client)
    roster_text = _format_roster(roster)
    recent_artifacts = await _get_recent_artifacts(client)

    history_text = ""
    if state["history"]:
        lines = []
        for h in state["history"][-4:]:  # 최근 4턴만
            lines.append(f"사용자: {h['user']}")
            lines.append(f"PM: {h['pm']}")
        history_text = "이전 대화:\n" + "\n".join(lines) + "\n\n"

    context = (
        f"{history_text}"
        f"팀 현황:\n{roster_text}\n\n"
        + (f"최근 완료 작업:\n{recent_artifacts}\n\n" if recent_artifacts else "")
        + f"사용자: {text}"
    )

    # 6턴 이상이면 LLM에 계획 확정 요청
    if ms["turns"] >= 6:
        context += "\n\n[시스템: 대화가 충분히 진행되었습니다. 구체적인 계획을 제안하고 proposed_plan을 반드시 포함하세요.]"

    result = await _call_llm(DISCUSS_PROMPT, context)
    reply = result.get("reply", "")
    proposed = result.get("proposed_plan")

    # 계획이 제안됐으면 SOLICITING → BRIEF_READY 전환 (비동기)
    if proposed:
        reply = reply + "\n\n잠시 팀 역량을 확인하고 브리프를 정리할게요."
        state["pending_plan"] = proposed
        asyncio.create_task(_solicit_and_finalize(room_id, proposed, client))

    await _send_chat(room_id, reply, client)
    state["history"].append({"user": text, "pm": result.get("reply", "")})


# ── WORKSPACE.md 헬퍼 ────────────────────────────────────────────

import pathlib

def _workspace_path(room_id: str) -> pathlib.Path:
    """방별 WORKSPACE.md 경로."""
    return pathlib.Path(SHARED_DIR) / room_id / "WORKSPACE.md"


def _ensure_workspace(room_id: str, brief: dict | None = None) -> str:
    """WORKSPACE.md 생성 또는 갱신. 반환값: 현재 파일 내용."""
    p = _workspace_path(room_id)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        content = f"""\
# WORKSPACE — {room_id}

## Vision
(pm이 논의 후 갱신합니다)

## Architecture
(결정사항이 생기면 여기에 기록됩니다)

## Current Sprint
(없음)

## Decisions
(없음)

## Artifacts
(완료된 태스크의 변경 파일이 여기에 기록됩니다)
"""
        p.write_text(content, encoding="utf-8")
        print(f"[PM] WORKSPACE.md 생성: {p}", flush=True)

    if brief:
        content = p.read_text(encoding="utf-8")
        # Current Sprint 섹션 갱신
        sprint_section = f"## Current Sprint\n{brief.get('brief', '')}\n"
        if "## Current Sprint" in content:
            import re
            content = re.sub(
                r"## Current Sprint\n.*?(?=\n## |\Z)",
                sprint_section,
                content,
                flags=re.DOTALL,
            )
        else:
            content += f"\n{sprint_section}"
        p.write_text(content, encoding="utf-8")
        print(f"[PM] WORKSPACE.md Current Sprint 갱신", flush=True)

    return p.read_text(encoding="utf-8")


def _append_artifacts(room_id: str, task_id: str, subject: str,
                       changed_files: list[str], decisions: list[str]) -> None:
    """완료 태스크 artifacts를 WORKSPACE.md에 추가."""
    p = _workspace_path(room_id)
    if not p.exists():
        return
    content = p.read_text(encoding="utf-8")
    entry = f"- `{task_id}` {subject}"
    if changed_files:
        entry += f"\n  - files: {', '.join(changed_files[:5])}"
    if decisions:
        entry += f"\n  - decisions: {' / '.join(decisions[:3])}"
    if "## Artifacts" in content:
        content = content.replace("## Artifacts\n(완료된 태스크의 변경 파일이 여기에 기록됩니다)",
                                  f"## Artifacts\n{entry}")
        content = content.replace("## Artifacts\n", f"## Artifacts\n{entry}\n")
    else:
        content += f"\n## Artifacts\n{entry}\n"
    p.write_text(content, encoding="utf-8")


def _build_task_prompt(task_def: dict) -> str:
    """6섹션 필드가 있으면 구조화된 프롬프트 조합, 없으면 기존 prompt 사용 (하위 호환)."""
    if task_def.get("task"):
        sections = [f"## TASK\n{task_def['task']}"]
        if task_def.get("expected_outcome"):
            sections.append(f"## EXPECTED OUTCOME\n{task_def['expected_outcome']}")
        if task_def.get("required_tools"):
            sections.append(f"## REQUIRED TOOLS\n{', '.join(task_def['required_tools'])}")
        if task_def.get("must_do"):
            items = "\n".join(f"- {x}" for x in task_def["must_do"])
            sections.append(f"## MUST DO\n{items}")
        if task_def.get("must_not_do"):
            items = "\n".join(f"- {x}" for x in task_def["must_not_do"])
            sections.append(f"## MUST NOT DO\n{items}")
        if task_def.get("context"):
            sections.append(f"## CONTEXT\n{task_def['context']}")
        return "\n\n".join(sections)
    return task_def.get("prompt", "")


def _local_task_id(task_def: dict, index: int, used: set[str]) -> str:
    """태스크에 계획 내부에서 안정적인 로컬 식별자를 부여한다.

    LLM이 준 'id'(또는 'ref'/'local_id')를 우선 사용하되, 비어있거나 이미 쓰인
    값이면 위치 기반 t{n}으로 대체하고 충돌 시 유니크화한다.
    """
    raw = task_def.get("id") or task_def.get("ref") or task_def.get("local_id")
    candidate = str(raw).strip() if raw else ""
    if not candidate or candidate in used:
        candidate = f"t{index + 1}"
    base, n = candidate, 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _plan_dependency_order(tasks_def: list[dict]) -> list[dict]:
    """LLM 계획의 blocked_by(로컬 참조)를 위상정렬하고 생성 메타를 만든다.

    서버 task_id는 POST /api/tasks 시점에야 생성되므로 LLM은 알 수 없다. 따라서
    LLM이 쓴 blocked_by는 '실제 id'가 아니라 계획 내부의 로컬 참조여야 한다. 이
    함수는 각 태스크에 안정적 로컬 id를 부여하고, blocked_by가 가리키는 in-plan
    선행 태스크를 찾아 위상정렬한다(LLM이 의존 태스크를 먼저 나열해도 안전).

    반환: 생성(create) 순서의 step dict 리스트 ::

        {"index": int, "local_id": str, "depends_on": str|None, "held_reason": str|None}

    held_reason 이 None이 아니면 의존성을 해석할 수 없는 태스크다. dispatch는 이를
    존재하지 않는 id에 blocked된 채 생성(=영원히 hang)하지 말고, 또한 조용히
    의존성을 떼고 실행(=순서 위반/결과 오염)하지도 말고, 사용자에게 surfaced 해야
    한다(fail-visible).
    """
    from collections import deque

    n = len(tasks_def)
    used: set[str] = set()
    local_ids: list[str] = []
    for i, td in enumerate(tasks_def):
        lid = _local_task_id(td, i, used)
        used.add(lid)
        local_ids.append(lid)
    id_to_index = {lid: i for i, lid in enumerate(local_ids)}

    # blocked_by를 in-plan 로컬 참조로 정규화한다.
    dep_index: list[int | None] = [None] * n   # 해석된 선행 태스크 인덱스
    held: list[str | None] = [None] * n         # 해석 실패 사유
    for i, td in enumerate(tasks_def):
        raw = td.get("blocked_by")
        if isinstance(raw, (list, tuple)):
            # 스키마(blocked_by: str)는 단일 의존만 표현 가능. 다중 blocker는
            # 엣지를 조용히 잃지 않도록 명시적으로 held 처리한다(별도 스키마 작업 필요).
            non_empty = [str(x).strip() for x in raw if str(x).strip()]
            if not non_empty:
                raw = None
            elif len(non_empty) == 1:
                raw = non_empty[0]
            else:
                held[i] = f"다중 blocker 미지원(scalar 스키마): {non_empty}"
                continue
        ref = str(raw).strip() if raw else ""
        if not ref:
            continue                                  # 의존성 없음 → pending
        if ref == local_ids[i]:
            held[i] = "자기 자신을 의존(self dependency)"
            continue
        if ref in id_to_index:
            dep_index[i] = id_to_index[ref]           # 정상 in-plan 의존성
        else:
            # placeholder("T-{...}"), 임의 "T-<uuid>", 미정의 로컬 id 등 → dangling
            held[i] = f"해석 불가한 blocked_by 참조: {ref!r}"

    # Kahn 위상정렬(단일 부모). held 태스크는 생성 대상이 아니므로 ready 큐에 들지
    # 않고, 그에 의존하는 태스크도 자연히 미배치로 남아 아래에서 surfaced 된다.
    indegree = [0] * n
    children: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if held[i] is None and dep_index[i] is not None:
            indegree[i] = 1
            children[dep_index[i]].append(i)

    ready = deque(i for i in range(n) if held[i] is None and indegree[i] == 0)
    order: list[int] = []
    while ready:
        i = ready.popleft()
        order.append(i)
        for c in children[i]:
            indegree[c] -= 1
            if indegree[c] == 0 and held[c] is None:
                ready.append(c)

    placed = set(order)
    steps: list[dict] = []
    for i in order:
        dep = local_ids[dep_index[i]] if dep_index[i] is not None else None
        steps.append({"index": i, "local_id": local_ids[i],
                      "depends_on": dep, "held_reason": None})
    # 미배치 태스크(=직접 held이거나, held/사이클 선행에 막힌 태스크)를 뒤에 둔다.
    for i in range(n):
        if i in placed:
            continue
        reason = held[i] or "선행 태스크가 미해결이거나 순환 의존성"
        steps.append({"index": i, "local_id": local_ids[i],
                      "depends_on": None, "held_reason": reason})
    return steps


async def _dispatch_plan(plan: dict, room_id: str, client: httpx.AsyncClient) -> None:
    """확정된 계획을 태스크로 변환하고 배정."""
    title = plan.get("title", "작업")
    tasks_def = plan.get("tasks", [])

    if not tasks_def:
        # tasks가 없으면 LLM으로 재생성
        roster = await _get_roster(client)
        context = (
            f"팀 현황:\n{_format_roster(roster)}\n\n"
            f"확정된 계획:\n{plan.get('brief', '')}"
        )
        result = await _call_llm(DISPATCH_PROMPT, context)
        tasks_def = result.get("tasks", [])

    # 배치 ID 생성
    batch_id = str(uuid.uuid4())[:8]
    created_ids = []

    # WORKSPACE.md 생성/갱신
    workspace_context = ""
    try:
        workspace_context = _ensure_workspace(room_id, brief=plan)
    except Exception as e:
        print(f"[PM] WORKSPACE.md 갱신 실패: {e}", file=sys.stderr)

    # workspace context를 task prompt에 주입 (300자 이내 요약)
    ws_prefix = ""
    if workspace_context:
        ws_lines = [l for l in workspace_context.splitlines()
                    if l.strip() and not l.startswith("#")][:8]
        ws_snippet = "\n".join(ws_lines)[:300]
        if ws_snippet:
            ws_prefix = f"[Workspace Context]\n{ws_snippet}\n\n"

    # 의존성 위상정렬: blocked_by(로컬 참조)를 *실제* 생성 task_id로 치환하기 위해
    # 선행 태스크부터 생성하면서 local_id → 실제 task_id 맵을 만든다.
    plan_steps = _plan_dependency_order(tasks_def)
    local_to_real: dict[str, str] = {}
    held_reports: list[tuple[str, str]] = []   # (subject, 보류 사유)

    if os.getenv("DIPEEN_PM_PROPOSAL_ONLY", "1").lower() not in ("0", "false", "no"):
        proposal_steps = []
        for step in plan_steps:
            task_def = tasks_def[step["index"]]
            subject = task_def.get("subject", "")
            if step["held_reason"]:
                held_reports.append((subject, step["held_reason"]))
                continue
            base_prompt = _build_task_prompt(task_def)
            prompt_with_ctx = ws_prefix + base_prompt
            provider = "codex" if str(task_def.get("required_role", "")).upper() in ("FE", "FRONTEND") else "claude"
            proposal_steps.append({
                "intent": f"{subject}\n\n{prompt_with_ctx}",
                "provider": task_def.get("provider") or provider,
                "workspace_root": os.getenv("DIPEEN_WORKSPACE_ROOT", ""),
                "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}],
            })
        if proposal_steps:
            r = await client.post(
                f"{API_URL}/api/proposals/plan",
                json={"room_id": room_id, "proposed_by": f"agent://team/{PM_AGENT_ID}", "plan": proposal_steps},
                headers=_auth_headers(),
                timeout=5,
            )
            r.raise_for_status()
            proposals_created = r.json()
            proposal_lines = "\n".join(f"- `{p['proposal_id']}` {p['intent'].splitlines()[0][:80]}"
                                       for p in proposals_created)
            await _send_chat(
                room_id,
                f"[OK] **{title}** 실행 제안을 생성했습니다. ({len(proposals_created)}개)\n\n"
                f"{proposal_lines}\n\n사람이 confirm해야 worker queue에 들어갑니다.",
                client,
            )
        if held_reports:
            held_lines = "\n".join(f"- ⚠️ {subj} — {reason}" for subj, reason in held_reports)
            await _send_chat(
                room_id,
                f"⚠️ 의존성을 해석할 수 없어 **보류된 제안 {len(held_reports)}개**:\n\n{held_lines}",
                client,
            )
        print(f"[PM] proposal-only dispatch 완료: {len(proposal_steps)}개 제안", flush=True)
        await _set_phase(room_id, "BRIEF_READY", client)
        return

    for step in plan_steps:
        task_def = tasks_def[step["index"]]
        subject = task_def.get("subject", "")

        # 의존성을 해석할 수 없는 태스크 → dangling block으로 생성하지 않고 surfaced.
        if step["held_reason"]:
            held_reports.append((subject, step["held_reason"]))
            print(f"[PM] 의존성 해석 실패 → 태스크 보류: {subject!r} ({step['held_reason']})",
                  file=sys.stderr)
            continue

        # 선행 태스크의 *실제* task_id로 blocked_by 치환.
        real_blocked_by = None
        if step["depends_on"] is not None:
            real_blocked_by = local_to_real.get(step["depends_on"])
            if real_blocked_by is None:
                # 선행 태스크 생성이 실패했음 → 의존을 만족할 수 없으므로 fail-closed.
                reason = f"선행 태스크 생성 실패 (dep={step['depends_on']})"
                held_reports.append((subject, reason))
                print(f"[PM] {reason} → 태스크 보류: {subject!r}", file=sys.stderr)
                continue

        try:
            base_prompt = _build_task_prompt(task_def)
            prompt_with_ctx = ws_prefix + base_prompt
            r = await client.post(
                f"{API_URL}/api/tasks",
                json={
                    "subject": subject,
                    "prompt": prompt_with_ctx,
                    "complexity": task_def.get("complexity"),  # Z-1: 카테고리 모델 라우팅
                    "required_role": task_def.get("required_role"),
                    "required_persona": task_def.get("required_persona"),
                    "required_skills": task_def.get("required_skills", []),
                    "blocked_by": real_blocked_by,
                    "created_by_agent": PM_AGENT_ID,
                },
                headers=_auth_headers(),
                timeout=5,
            )
            if r.status_code == 201:
                task_id = r.json()["task_id"]
                created_ids.append(task_id)
                local_to_real[step["local_id"]] = task_id
                TASK_BATCH[task_id] = {
                    "room_id": room_id,
                    "subject": subject,
                    "batch_id": batch_id,
                }
                # wrap 계약: 결정 카드가 고정한 경계를 봉투로 보관 → 보고 시 Gatekeeper가 강제.
                # 카드가 범위를 안 줘도 비밀/키 deny(BYOK 불변식)는 항상 적용된다.
                try:
                    from app.schemas.runner import TaskEnvelope
                    from app.services.scope_policy import default_scope_claims
                    from app.services import run_journal
                    _env = TaskEnvelope(
                        task_id=task_id,
                        team_id=os.getenv("DIPEEN_TEAM_ID", "default"),
                        room_id=room_id,
                        subject=subject,
                        prompt=prompt_with_ctx,
                        scope_claims=default_scope_claims(task_def),
                        decision_id=str(plan.get("decision_id") or batch_id),
                    )
                    TASK_ENVELOPE[task_id] = _env
                    # Run Journal: 배정 사실을 팀 소유 로그에 남긴다(감사·복구).
                    run_journal.journal_event(
                        room_id, "dispatch",
                        {"task_id": task_id, "subject": subject,
                         "deny_paths": _env.scope_claims.deny_paths,
                         "allow_paths": _env.scope_claims.allow_paths,
                         "decision_id": _env.decision_id},
                        trace_id=_env.trace_id,
                    )
                except Exception as e:
                    print(f"[PM] envelope/journal 실패(비치명): {e}", file=sys.stderr)
        except Exception as e:
            print(f"[PM] 태스크 생성 실패: {e}", file=sys.stderr)

    if created_ids:
        BATCH_STATE[batch_id] = {
            "room_id": room_id,
            "title": title,
            "total": len(created_ids),
            "done": 0,
            "errors": 0,
            "results": [],
        }

    task_list = "\n".join(f"- `{tid}` {TASK_BATCH.get(tid, {}).get('subject', '')}"
                          for tid in created_ids)
    await _send_chat(
        room_id,
        f"[OK] **{title}** 작업을 배정했습니다. ({len(created_ids)}개)\n\n{task_list}",
        client,
    )
    # 의존성을 해석할 수 없어 보류된 태스크를 surfaced (silent hang/순서 위반 방지).
    if held_reports:
        held_lines = "\n".join(f"- ⚠️ {subj} — {reason}" for subj, reason in held_reports)
        await _send_chat(
            room_id,
            f"⚠️ 의존성을 해석할 수 없어 **보류된 태스크 {len(held_reports)}개**:\n\n{held_lines}\n\n"
            f"blocked_by가 실제 선행 태스크의 로컬 id를 가리키지 않습니다. 계획을 다시 확인해 주세요.",
            client,
        )
        print(f"[PM] 보류된 태스크 {len(held_reports)}개 (의존성 미해결)", file=sys.stderr)
    print(f"[PM] 배정 완료: {len(created_ids)}개 태스크 (batch={batch_id})", flush=True)
    await _set_phase(room_id, "EXECUTING", client)


# ── 태스크 완료 능동 감지 ────────────────────────────────────────

async def _gatekeep_task(task_id: str, status: str, event: dict,
                         client: httpx.AsyncClient):
    """배정 시 보관한 TaskEnvelope에 비춰 RunReport를 판정한다(출구 게이트).

    runner가 'done'이라 자기보고해도, 범위(scope_claims)를 넘었으면 HQ는 accept 하지 않는다.
    반환: (GatekeeperVerdict|None, TaskEnvelope|None). 봉투는 pop하지 않는다(retry가 재사용).
    """
    envelope = TASK_ENVELOPE.get(task_id)
    if envelope is None:
        return None, None
    try:
        from app.schemas.runner import RunReport
        from app.services.gatekeeper import gatekeep
    except Exception as e:
        print(f"[PM] Gatekeeper import 실패(비치명): {e}", file=sys.stderr)
        return None, envelope

    changed_files: list = []
    key_decisions: list = []
    promise = None
    checks: dict = {}
    try:
        resp = await client.get(f"{API_URL}/api/tasks/{task_id}",
                                headers=_auth_headers(), timeout=5)
        tjson = resp.json()
        arts = (tjson.get("result") or {}).get("artifacts") or {}
        changed_files = arts.get("changed_files") or []
        key_decisions = arts.get("key_decisions") or []
        promise = arts.get("completion_promise") or tjson.get("completion_promise")
        checks = arts.get("checks") or {}   # Node가 보낸 pytest/ruff 결과(있으면)
    except Exception:
        pass
    # API가 done으로 확정 = J-1 완료 약속(<promise>DONE</promise>) 충족.
    if promise is None and status == "done":
        promise = envelope.completion_promise

    try:
        report = RunReport(
            task_id=task_id,
            agent_id=event.get("agent_id") or event.get("from_agent") or "unknown",
            runner=envelope.runner,
            status=status,
            completion_promise=promise,
            changed_files=changed_files,
            scope_diff=changed_files,
            key_decisions=key_decisions,
            trace_id=envelope.trace_id,
        )
        verdict = gatekeep(envelope, report, checks)   # Node가 RunReport.checks 보내면 DETERMINISTIC_FAIL 강제
        if verdict.verdict != "accept":
            print(f"[PM] Gatekeeper {verdict.verdict}: {task_id} — {verdict.reason}",
                  flush=True)
        # Run Journal: 판정 사실을 남긴다(누가 무엇을 만졌고 HQ가 어떻게 판정했나).
        try:
            from app.services import run_journal
            run_journal.journal_event(
                envelope.room_id, "verdict",
                {"task_id": task_id, "verdict": verdict.verdict,
                 "failure_code": verdict.failure_code, "status": status,
                 "changed_files": changed_files, "scope_violations": verdict.scope_violations,
                 "reason": verdict.reason},
                trace_id=envelope.trace_id,
            )
        except Exception:
            pass
        return verdict, envelope
    except Exception as e:
        print(f"[PM] Gatekeeper 평가 실패(비치명): {e}", file=sys.stderr)
        return None, envelope


async def _remediate_retry(envelope, verdict, decision, batch_id, room_id,
                           client: httpx.AsyncClient) -> bool:
    """같은 태스크를 attempt+1로 재배정한다. Remediation Packet은 *이 태스크 envelope에만*
    append — 전역 시스템 프롬프트는 건드리지 않는다(도돌이표 방지의 핵심). 같은 batch 슬롯 유지."""
    from app.services import run_journal
    new_prompt = envelope.prompt + "\n\n" + (decision.packet or "")
    try:
        r = await client.post(
            f"{API_URL}/api/tasks",
            json={"subject": envelope.subject, "prompt": new_prompt, "created_by_agent": PM_AGENT_ID},
            headers=_auth_headers(), timeout=5,
        )
        if r.status_code != 201:
            return False
        new_id = r.json()["task_id"]
    except Exception as e:
        print(f"[PM] remediation 재배정 실패: {e}", file=sys.stderr)
        return False

    TASK_BATCH[new_id] = {"room_id": room_id, "subject": envelope.subject, "batch_id": batch_id}
    TASK_ENVELOPE[new_id] = envelope.model_copy(update={"task_id": new_id, "attempt": decision.attempt})
    # 진전 단조성 가드: 다음 시도가 *같은 사유*로 또 실패하면 사람에게.
    REMEDIATION_STATE[envelope.trace_id] = {"attempt": decision.attempt, "prev_reason": verdict.reason}
    try:
        run_journal.journal_event(
            room_id, "remediation",
            {"task_id": envelope.task_id, "retry_task_id": new_id,
             "attempt": decision.attempt, "failure_code": decision.failure_code},
            trace_id=envelope.trace_id,
        )
    except Exception:
        pass
    await _send_chat(
        room_id,
        f"🔄 `{envelope.task_id}` **{envelope.subject}** 자동 재시도 {decision.attempt} "
        f"(복구: {decision.failure_code})",
        client,
    )
    return True


async def on_task_update(event: dict, client: httpx.AsyncClient) -> None:
    """task_update 이벤트 수신 → 배치 완료 시 자동 보고."""
    task_id = event.get("task_id")
    status = event.get("status")

    if task_id not in TASK_BATCH:
        return
    if status not in ("done", "error", "cancelled"):
        return

    batch_info = TASK_BATCH.pop(task_id)
    batch_id = batch_info["batch_id"]
    room_id = batch_info["room_id"]
    subject = batch_info["subject"]

    if batch_id not in BATCH_STATE:
        return

    # ── 출구 게이트 + 자동 복구(OCDR: Classify→Decide→Remediate) ──
    # runner가 'done'이라 보고해도 범위 위반/검증 실패면 accept 안 함. 그리고 *사람이 아니라
    # 정책*이 다음 행동을 정한다: 자동 재시도(bounded) / 사람 / 분해 / 종료.
    verdict, envelope = await _gatekeep_task(task_id, status, event, client)
    TASK_ENVELOPE.pop(task_id, None)   # 이 task_id의 봉투는 소비됨(retry면 새 봉투 생성)

    decision = None
    if verdict is not None and envelope is not None:
        try:
            from app.services.remediation import decide_remediation
            from app.services import run_journal
            prev = REMEDIATION_STATE.get(envelope.trace_id, {})
            try:
                recurrence = run_journal.count_failures(room_id, verdict.failure_code)
            except Exception:
                recurrence = 0
            decision = decide_remediation(verdict, attempt=envelope.attempt,
                                          prev_reason=prev.get("prev_reason"), recurrence=recurrence)
        except Exception as e:
            print(f"[PM] remediation 결정 실패(비치명): {e}", file=sys.stderr)

    # 자동 재시도: 이 태스크를 카운트하지 않고 같은 batch 슬롯에 재배정 → batch는 retry 완료를 기다린다.
    if decision is not None and decision.action == "retry":
        if await _remediate_retry(envelope, verdict, decision, batch_id, room_id, client):
            return
        # 재배정 실패 시 사람으로 fall-through
        decision.action = "needs_human"

    # 최종 라우팅 (decision이 없으면 verdict 기반 보수적 기본값)
    action = decision.action if decision is not None else (
        "accept" if (status == "done" and (verdict is None or verdict.verdict == "accept")) else "stop"
    )
    accepted = (action == "accept" and status == "done")
    if envelope is not None and action != "retry":
        REMEDIATION_STATE.pop(envelope.trace_id, None)   # 체인 종료 — 상태 정리

    batch = BATCH_STATE[batch_id]
    if accepted:
        batch["done"] += 1
    else:
        batch["errors"] += 1
    batch["results"].append({
        "task_id": task_id,
        "subject": subject,
        "status": status,
        "verdict": (verdict.verdict if verdict else "accept"),
        "failure_code": (verdict.failure_code if verdict else "NONE"),
        "action": action,
        "verdict_reason": (decision.reason if decision else (verdict.reason if verdict else None)),
        "human_card_prompt": (verdict.human_card_prompt if verdict else None),
        "pr_url": event.get("pr_url"),
    })

    completed = batch["done"] + batch["errors"]

    # 단일 태스크 결과 알림 (정책 판정 반영)
    if accepted:
        pr_note = f" → [PR]({event.get('pr_url')})" if event.get("pr_url") else ""
        await _send_chat(room_id, f"[OK] `{task_id}` **{subject}** 완료{pr_note}", client)
    elif action in ("needs_human", "decompose"):
        icon = "🙋" if action == "needs_human" else "🧩"
        label = "사람 승인 필요" if action == "needs_human" else "PM 분해 필요"
        detail = (verdict.human_card_prompt if (verdict and verdict.human_card_prompt)
                  else (decision.reason if decision else "검토 필요"))
        await _send_chat(room_id, f"{icon} `{task_id}` **{subject}** — {label}\n\n{detail}", client)
    else:  # stop / 보수적 fallback
        reason = (decision.reason if decision else (verdict.reason if verdict else None)) or "실행 오류"
        await _send_chat(room_id, f"⛔ `{task_id}` **{subject}** 종료 — {reason}", client)

    # 배치 전체 완료 → 종합 보고
    if completed >= batch["total"]:
        await _send_batch_summary(batch_id, client)


async def _send_batch_summary(batch_id: str, client: httpx.AsyncClient) -> None:
    """배치 내 모든 태스크 완료 → 종합 결과 + artifacts 요약 채팅 전송."""
    batch = BATCH_STATE.pop(batch_id, None)
    if not batch:
        return

    room_id = batch["room_id"]
    title = batch["title"]
    done = batch["done"]
    errors = batch["errors"]
    results = batch["results"]

    # 완료된 태스크들의 artifacts 수집 (Result Distillation) — 정책이 accept한 것만.
    artifact_lines = []
    for r in results:
        if r.get("action", "accept") != "accept":
            continue
        try:
            resp = await client.get(
                f"{API_URL}/api/tasks/{r['task_id']}",
                headers=_auth_headers(),
                timeout=5,
            )
            arts = resp.json().get("result", {}).get("artifacts") or {}
            files = arts.get("changed_files", [])
            decisions = arts.get("key_decisions", [])
            if files:
                artifact_lines.append(f"  - 변경: {', '.join(files[:3])}")
            if decisions:
                artifact_lines.append(f"  - 결정: {' / '.join(decisions[:2])}")
            # WORKSPACE.md 아티팩트 기록
            try:
                _append_artifacts(room_id, r["task_id"], r["subject"], files, decisions)
            except Exception:
                pass
        except Exception:
            pass

    summary_parts = [
        f"## [END] **{title}** 완료 보고",
        f"성공 {done}개 / 오류 {errors}개",
    ]
    if artifact_lines:
        summary_parts.append("\n**변경 사항:**\n" + "\n".join(artifact_lines))
    # 정책 판정별 분류 (자동 복구가 해결 못해 사람/PM에게 올라온 것 = 결정 카드 재등장 대상)
    human_items = [r for r in results if r.get("action") in ("needs_human", "decompose")]
    if human_items:
        nh_lines = "\n".join(
            f"- {'🙋' if r.get('action') == 'needs_human' else '🧩'} {r['subject']} — {r.get('verdict_reason') or '검토 필요'}"
            for r in human_items
        )
        summary_parts.append(f"\n**사람/PM 개입 대기:**\n{nh_lines}")
    stopped = [r["subject"] for r in results if r.get("action") == "stop"]
    if stopped:
        summary_parts.append(f"\n**종료/실패:** {', '.join(stopped)}")
    summary_parts.append("\n다음 작업이 있으면 말씀해 주세요.")

    await _send_chat(room_id, "\n".join(summary_parts), client)
    await _set_phase(room_id, "DONE", client)
    print(f"[PM] 배치 {batch_id} 종합 보고 완료", flush=True)


# ── agent_question 처리 ───────────────────────────────────────────

async def handle_agent_question(event: dict, client: httpx.AsyncClient) -> None:
    from_agent = event.get("from_agent", "unknown")
    content = event.get("content", "")
    msg_id = event.get("id")
    task_id = event.get("task_id")

    print(f"[PM] {from_agent}의 질문: {content[:60]}", flush=True)

    try:
        import anthropic
        ac = anthropic.AsyncAnthropic()
        resp = await ac.messages.create(
            model=MODEL,
            max_tokens=512,
            system="당신은 PM 에이전트입니다. 팀원의 질문에 간결하게 답변하세요.",
            messages=[{"role": "user", "content": content}],
        )
        answer = resp.content[0].text.strip()
    except Exception as e:
        answer = f"[PM] 답변 생성 실패: {e}"

    try:
        await client.post(
            f"{API_URL}/api/agents/{PM_AGENT_ID}/message",
            json={
                "to_agent_id": from_agent,
                "task_id": task_id,
                "message_type": "message",
                "content": answer,
                "reply_to": msg_id,
            },
            headers=_auth_headers(),
            timeout=5,
        )
    except Exception as e:
        print(f"[PM] 답변 전송 실패: {e}", file=sys.stderr)

    # 질문/답변 내용을 채팅에도 공유
    room_id = "general"
    if task_id and task_id in TASK_BATCH:
        room_id = TASK_BATCH[task_id]["room_id"]

    await _send_chat(
        room_id,
        f"[msg] **{from_agent}** 질문: {content}\n\n**PM 답변:** {answer}",
        client,
    )


async def _locked_handle(text: str, room_id: str,
                         client: httpx.AsyncClient,
                         lock: asyncio.Lock) -> None:
    """per-room 락을 잡고 handle_user_message 실행."""
    async with lock:
        await handle_user_message(text, room_id, client)


# ── 메인 루프 ─────────────────────────────────────────────────────

async def pm_loop() -> None:
    ws_url = f"{WS_URL}/ws/events"
    print(f"[PM Loop] 시작 -- {ws_url}", flush=True)

    async with httpx.AsyncClient() as http_client:
        while True:
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers=_auth_headers(),
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    print("[PM Loop] WS 연결됨", flush=True)
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        ev_type = event.get("type")

                        if ev_type == "chat_message":
                            # pm/agent 메시지 무시 (재귀 방지)
                            if event.get("sender_type") in ("agent", "pm"):
                                continue
                            if event.get("sender") in (PM_AGENT_ID, "pm-loop"):
                                continue
                            text = (event.get("text") or "").strip()
                            if not text:
                                continue
                            room_id = event.get("room_id", "general")
                            # 라우팅: 응답 불필요한 메시지 무시
                            if not _should_respond(text, room_id):
                                print(f"[PM] skip (routing): {text[:40]}", flush=True)
                                continue
                            # per-room 락: 이미 응답 중이면 큐잉하지 않고 드롭
                            lock = _room_lock(room_id)
                            if lock.locked():
                                print(f"[PM] skip (locked): {text[:40]}", flush=True)
                                continue
                            asyncio.create_task(
                                _locked_handle(text, room_id, http_client, lock)
                            )

                        elif ev_type == "meeting_mode":
                            # 모드 전환 (UI 셀렉터 → API → WS → pm_loop)
                            room_id = event.get("room_id", "general")
                            new_mode = event.get("mode", "plan")
                            ms = _get_ms(room_id)
                            ms["mode"] = new_mode
                            # 브레인스토밍으로 전환 시 phase/plan 초기화
                            if new_mode == "brainstorm":
                                ms["turns"] = 0
                                ROOM_STATE.pop(room_id, None)
                            print(f"[PM] 모드 전환: {room_id} → {new_mode}", flush=True)

                        elif ev_type == "task_update":
                            # 능동 완료 감지 (G-2)
                            asyncio.create_task(
                                on_task_update(event, http_client)
                            )

                        elif ev_type == "agent_message":
                            if event.get("message_type") == "question":
                                asyncio.create_task(
                                    handle_agent_question(event, http_client)
                                )

                        elif ev_type == "pm_config_update":
                            # P3: PM 설정 실시간 반영
                            if event.get("response_style"):
                                _PM_RUNTIME["response_style"] = event["response_style"]
                            if event.get("auto_execute") is not None:
                                _PM_RUNTIME["auto_execute"] = event["auto_execute"]
                            if event.get("skip_review") is not None:
                                _PM_RUNTIME["skip_review"] = event["skip_review"]
                            print(f"[PM] config 변경: {_PM_RUNTIME}", flush=True)

            except (websockets.ConnectionClosed, OSError) as e:
                print(f"[PM Loop] 연결 끊김: {e} -- 3초 후 재연결", file=sys.stderr)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[PM Loop] 오류: {e} -- 5초 후 재시작", file=sys.stderr)
                await asyncio.sleep(5)


async def _main() -> None:
    """pm_loop + telegram_bot 동시 실행."""
    try:
        from telegram_bot import telegram_bot_loop  # type: ignore
        await asyncio.gather(pm_loop(), telegram_bot_loop())
    except (ImportError, Exception):
        await pm_loop()


if __name__ == "__main__":
    asyncio.run(_main())
