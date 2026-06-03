"""D-2: 토큰 사용량 집계 API."""

from datetime import datetime, timezone, date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageLog, Agent
from app.db.session import get_db
from app.routers.auth import get_team_id

router = APIRouter()

# Provider별 토큰 단가 (per 1M tokens, 입출력 평균)
COST_PER_1M: dict[str, float] = {
    "claude": 3.0,
    "gemini": 0.075,
    "ollama": 0.0,
    "openai": 2.5,
}


def _provider_from_model(model: str | None) -> str:
    if not model:
        return "unknown"
    m = model.lower()
    if "claude" in m:
        return "claude"
    if "gemini" in m:
        return "gemini"
    if "gpt" in m or "o1" in m or "o3" in m:
        return "openai"
    if "ollama" in m or "llama" in m or "qwen" in m or "mistral" in m:
        return "ollama"
    return "unknown"


@router.get("/summary")
async def usage_summary(
    period_days: int = 30,
    db: AsyncSession = Depends(get_db),
    team_id: str = Depends(get_team_id),
):
    """팀 전체 토큰 사용량 집계.
    Returns: total_tokens, today_tokens, by_agent, estimated_cost_usd, by_agent_model
    """
    period_start = datetime.now(timezone.utc) - timedelta(days=period_days)

    # period 내 전체 합계
    total_stmt = select(func.sum(UsageLog.token_count)).where(
        UsageLog.team_id == team_id,
        UsageLog.created_at >= period_start,
    )
    total_result = await db.execute(total_stmt)
    total_tokens: int = total_result.scalar_one() or 0

    # 오늘 합계
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    today_stmt = select(func.sum(UsageLog.token_count)).where(
        UsageLog.team_id == team_id,
        UsageLog.created_at >= today_start,
    )
    today_result = await db.execute(today_stmt)
    today_tokens: int = today_result.scalar_one() or 0

    # 에이전트별 합계 + 모델
    by_agent_stmt = (
        select(
            Agent.agent_id,
            func.sum(UsageLog.token_count).label("tokens"),
            func.max(UsageLog.model).label("model"),
        )
        .join(Agent, Agent.id == UsageLog.agent_id)
        .where(
            UsageLog.team_id == team_id,
            UsageLog.created_at >= period_start,
        )
        .group_by(Agent.agent_id)
    )
    by_agent_result = await db.execute(by_agent_stmt)
    rows = by_agent_result.all()

    by_agent: dict[str, int] = {}
    by_agent_model: dict[str, str] = {}
    estimated_cost_usd = 0.0

    for row in rows:
        tokens = row.tokens or 0
        by_agent[row.agent_id] = tokens
        by_agent_model[row.agent_id] = row.model or "unknown"
        provider = _provider_from_model(row.model)
        cost_per_1m = COST_PER_1M.get(provider, 0.0)
        estimated_cost_usd += (tokens / 1_000_000) * cost_per_1m

    return {
        "period_days": period_days,
        "total_tokens": total_tokens,
        "today_tokens": today_tokens,
        "by_agent": by_agent,
        "by_agent_model": by_agent_model,
        "estimated_cost_usd": round(estimated_cost_usd, 6),
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
