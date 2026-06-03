"""
M-2: Agent Capability Manifest 서비스.

에이전트 등록 시 DIPEEN_AGENTS.md를 자동 갱신.
PM이 태스크 배정 결정 시 참조하는 인간 가독성 명세 파일.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent

# manifest 파일 위치: DIPEEN_WORKSPACE 환경변수 또는 프로젝트 루트
_WORKSPACE = Path(os.environ.get("DIPEEN_WORKSPACE", ".")).resolve()
MANIFEST_PATH = _WORKSPACE / "DIPEEN_AGENTS.md"

_ROLE_HINTS: dict[str, str] = {
    "FE":  "UI/UX 구현, React/Vue 컴포넌트, CSS. spec이 구체적일 때 최적.",
    "BE":  "API 설계, DB 모델링, 비즈니스 로직. 인터페이스 계약 먼저 확정 후 배정.",
    "QA":  "테스트 작성, 버그 재현, 회귀 검증. 구현 완료 후 배정.",
    "PM":  "요구사항 분석, 태스크 분해. 모호한 요청 시 먼저 개입.",
    "DEVOPS": "CI/CD, Docker, 배포 자동화. 인프라 변경 태스크에 배정.",
}


def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "anthropic"
    if "gemini" in m:
        return "gemini"
    if "gpt" in m or "o1" in m or "o3" in m:
        return "openai"
    if "kimi" in m or "moonshot" in m:
        return "kimi"
    if "qwen" in m:
        return "qwen"
    if "llama" in m or "mistral" in m or "phi" in m:
        return "ollama"
    return "unknown"


def _format_agent_block(agent: Agent) -> str:
    meta = agent.metadata_json or {}
    model = meta.get("model", "unknown")
    skills = meta.get("skills", [])
    mcps = meta.get("mcps", [])
    personas = meta.get("personas", ["coder"])
    provider = meta.get("llm_provider") or _infer_provider(model)
    role = (agent.role or "unknown").upper()
    hint = _ROLE_HINTS.get(role, "범용 에이전트.")

    lines = [
        f"## {agent.agent_id}",
        f"model: {model} | provider: {provider} | role: {role}",
        f"skills: {', '.join(skills) if skills else '미설정'}",
        f"mcps: {', '.join(mcps) if mcps else '없음'}",
        f"personas: {', '.join(personas)}",
        f"status: {agent.status}",
        f"delegation_hint: {hint}",
    ]
    return "\n".join(lines)


async def update_agents_manifest(db: AsyncSession, team_id: str) -> None:
    """팀 소속 에이전트 목록 → DIPEEN_AGENTS.md 갱신. 실패 시 무시."""
    try:
        result = await db.execute(
            select(Agent)
            .where(Agent.team_id == team_id, Agent.status != "offline")
            .order_by(Agent.role, Agent.agent_id)
        )
        agents = result.scalars().all()

        if not agents:
            return

        blocks = [
            "# DIPEEN_AGENTS — 에이전트 역량 명세",
            f"# team: {team_id} | 자동 갱신됨 (에이전트 등록 시)",
            "# PM이 태스크 배정 시 이 파일을 참조합니다. 수동 수정 가능.",
            "",
        ]
        for agent in agents:
            blocks.append(_format_agent_block(agent))
            blocks.append("")

        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text("\n".join(blocks), encoding="utf-8")
    except Exception as e:
        # best-effort: 실패해도 에이전트 등록은 정상 진행
        print(f"[manifest] 갱신 실패 (무시): {e}", flush=True)
