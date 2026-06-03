"""Team network graph — ProjectAgent 흡수 (P0-B).

에이전트를 노드로, parent_agent_id를 가상 엣지로 노출한다.
그래프 필드는 agents.metadata_json에 저장(마이그레이션 0):
  node_type(ai|human), node_class(pm|agent), parent_agent_id, pos_x, pos_y,
  accent_color, stat_label, name, user_id(human 노드 ↔ 실제 멤버)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import Agent
from app.db.session import async_session
from app.routers.auth import get_team_id
from app.routers.events import broadcast

router = APIRouter()


def _node(a: Agent) -> dict:
    m = a.metadata_json or {}
    return {
        "id": a.agent_id,
        "node_class": m.get("node_class", "agent"),
        "type": m.get("node_type", "ai"),
        "name": m.get("name", a.agent_id),
        "role": a.role,
        "status": a.status,
        "accent": m.get("accent_color"),
        "stat": m.get("stat_label", ""),
        "pos_x": m.get("pos_x", 0),
        "pos_y": m.get("pos_y", 0),
        "parent_id": m.get("parent_agent_id"),
        "user_id": m.get("user_id"),
    }


@router.get("/nodes")
async def get_nodes(team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        rows = (await db.execute(select(Agent).where(Agent.team_id == team_id))).scalars().all()
    nodes = [_node(a) for a in rows]
    edges = [
        {"id": f"{n['id']}_edge", "from": n["parent_id"], "to": n["id"]}
        for n in nodes
        if n["parent_id"]
    ]
    return {"nodes": nodes, "edges": edges}


class Position(BaseModel):
    pos_x: float
    pos_y: float


@router.patch("/nodes/{agent_id}/position")
async def set_position(agent_id: str, pos: Position, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        a = (
            await db.execute(
                select(Agent).where(Agent.team_id == team_id, Agent.agent_id == agent_id)
            )
        ).scalar_one_or_none()
        if a is None:
            raise HTTPException(404, "agent not found")
        # JSON 컬럼은 in-place mutation 미감지 → 새 dict 재대입 필수
        meta = dict(a.metadata_json or {})
        meta["pos_x"], meta["pos_y"] = pos.pos_x, pos.pos_y
        a.metadata_json = meta
        await db.commit()
    await broadcast({"type": "node_moved", "node_id": agent_id, "pos_x": pos.pos_x, "pos_y": pos.pos_y})
    return {"ok": True}
