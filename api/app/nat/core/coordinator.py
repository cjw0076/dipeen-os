"""Coordinator (head agent) — propose-only 분해/라우팅 reasoning.

3관점 합의(Vault `decisions/2026-06-03`): **host 상주 head 프로세스는 금지** — 죽인 pm_loop의 부활이고
Core 실행0·BYOK·사람승인 경계를 동시에 깬다. 대신 head = **worker 평면의 propose-only reasoner**:

- LLM 호출은 *주입*(worker가 BYOK로 자기 provider 실행) — **Core는 키 0**, 인터페이스+propose-only 계약만 소유.
- 출력 = `ActionCandidate[]`(close_meeting 후보와 동형). **enqueue/confirm 절대 안 함**(사람/정책 게이트 유지).
- `classify_message`(규칙기반 v0)의 LLM 대체 seam — 한 아이디어를 *여러* task로 분해(규칙기반은 1메시지=1후보).
- 환각 방지: 후보는 `source_message_ids`로 출처 추적, 모르는 role/provider는 안전 기본 정정, 검증/승인은 사람.

경계: 이 모듈은 queue/conductor/confirm을 import하지 않는다 — 구조적으로 실행 경로에 손댈 수 없다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from ..contracts import ActionCandidate, Message

# room transcript(str) → [{intent, title?, role?, provider?, repo?}, ...]. worker가 BYOK LLM으로 채운다.
LLMDecompose = Callable[[str], list[dict[str, Any]]]
_ROLES = {"frontend", "backend", "qa", "integrator", "memory"}
_PROVIDERS = {"claude", "codex", "omo", "hermes", "fake"}


def render_transcript(messages: list[Message]) -> str:
    """회의 메시지 → 분해 reasoning용 LLM 입력 transcript."""
    return "\n".join(f"- {m.body}" for m in messages if m.body)


def decompose_prompt(transcript: str) -> str:
    """worker가 자기 provider(claude/codex)에 줄 분해 프롬프트.

    JSON만 요구 + **파일 생성/수정 금지**(분해는 reasoning, side-effect 0 — 코드 변경은 별도 task의 일).
    """
    return (
        "You are a team coordinator. Read the meeting below and decompose it into concrete, independent tasks.\n"
        "Output ONLY a JSON array — no prose, no markdown fences. Each item is an object:\n"
        '  {"intent": "<one concrete task>", "title": "<short>", '
        '"role": "frontend|backend|qa|integrator", "provider": "claude|codex", "repo": "<repo slug, optional>"}.\n'
        "Do NOT create or edit any files. Return only the JSON plan.\n\n"
        f"=== MEETING ===\n{transcript}\n=== END MEETING ==="
    )


def parse_llm_plan(text: str) -> list[dict[str, Any]]:
    """LLM 출력 텍스트에서 JSON 배열을 추출(마크다운 펜스/잡설 허용). 실패하면 [](크래시 금지 — 사람이 수동 분해)."""
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if fenced:
        blob = fenced.group(1)
    else:
        start, end = text.find("["), text.rfind("]")
        blob = text[start:end + 1] if 0 <= start < end else ""
    if not blob:
        return []
    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def decompose(messages: list[Message], *, llm: LLMDecompose) -> list[ActionCandidate]:
    """회의 → 작업 후보(propose-only). LLM이 분해(worker에서 실행), 여기선 결과를 ActionCandidate로 정규화·검증.

    **enqueue/confirm 0 — 후보만.** 모르는 role/provider는 안전 기본으로 정정(거짓 라우팅 방지),
    빈/비정형 항목은 버림, source_message_ids로 출처 추적(환각 방지 — 검증/승인은 사람).
    """
    ids = [m.message_id for m in messages]
    raw = llm(render_transcript(messages)) or []
    out: list[ActionCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        intent = str(item.get("intent") or "").strip()
        if not intent:
            continue
        role = item.get("role")
        provider = item.get("provider")
        repo = item.get("repo")
        out.append(ActionCandidate(
            source_message_ids=ids,
            title=str(item.get("title") or intent)[:48],
            intent=intent,
            suggested_role=role if role in _ROLES else None,            # 모르는 role → None(사람이 확정)
            suggested_provider=provider if provider in _PROVIDERS else "claude",  # 모르는 provider → 안전 기본
            scope={"repo": repo} if repo else {},
        ))
    return out
