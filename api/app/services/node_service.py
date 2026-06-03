"""프로젝트 그래프 노드 서비스 — Leekuejea ProjectAgent에서 흡수, dipeen async로 포팅.

핵심(가져온 가치): "pm" 부모 별칭 · 삭제 시 cascade reparent(자식이 삭제노드의 부모를 입양) ·
seed_pm_node(PM 노드 멱등 생성). 영속 위치/계층을 프로젝트 단위로 보존한다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Node
from app.schemas.node import NodeCreate, NodeOut, NodeUpdate


async def _pm_id(db: AsyncSession, project_id: str) -> str | None:
    return (await db.execute(
        select(Node.id).where(Node.project_id == project_id, Node.node_class == "pm").limit(1)
    )).scalar_one_or_none()


def _resolve_parent(parent_input: str | None, pm_id: str | None) -> str | None:
    """"pm" 별칭 → PM 노드 uuid. 그 외엔 그대로."""
    if parent_input is None or parent_input == "pm":
        return pm_id
    return parent_input


def _to_out(node: Node, pm_id: str | None) -> NodeOut:
    parent = node.parent_id
    if parent and parent == pm_id:
        parent = "pm"
    return NodeOut(
        id=node.id, project_id=node.project_id, parent_id=parent, agent_id=node.agent_id,
        node_class=node.node_class, type=node.node_type, name=node.name, role=node.role_label,
        status=node.status, accent=node.accent_color, stat=node.stat_label,
        pos_x=node.pos_x, pos_y=node.pos_y,
    )


async def list_nodes(db: AsyncSession, project_id: str) -> list[NodeOut]:
    pm = await _pm_id(db, project_id)
    rows = (await db.execute(
        select(Node).where(Node.project_id == project_id).order_by(Node.created_at)
    )).scalars().all()
    return [_to_out(n, pm) for n in rows]


async def graph(db: AsyncSession, project_id: str) -> dict:
    """nodes + edges — 기존 /api/graph/nodes(GraphNode) 모양과 동일하게."""
    nodes = await list_nodes(db, project_id)
    edges = [{"id": f"{n.id}_edge", "from": (None if n.parent_id == "pm" else n.parent_id) or _pm_sentinel(nodes), "to": n.id}
             for n in nodes if n.parent_id]
    return {"nodes": [n.model_dump() for n in nodes], "edges": [e for e in edges if e["from"]]}


def _pm_sentinel(nodes: list[NodeOut]) -> str | None:
    pm = next((n for n in nodes if n.node_class == "pm"), None)
    return pm.id if pm else None


async def create_node(db: AsyncSession, project_id: str, data: NodeCreate) -> NodeOut:
    pm = await _pm_id(db, project_id)
    node = Node(
        project_id=project_id, node_class="agent", node_type=data.type, name=data.name,
        role_label=data.role, status=data.status, accent_color=data.accent, stat_label=data.stat,
        agent_id=data.agent_id, parent_id=_resolve_parent(data.parent_id, pm),
        pos_x=data.pos_x, pos_y=data.pos_y,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return _to_out(node, pm)


async def update_node(db: AsyncSession, node_id: str, project_id: str, data: NodeUpdate) -> NodeOut | None:
    pm = await _pm_id(db, project_id)
    node = (await db.execute(
        select(Node).where(Node.id == node_id, Node.project_id == project_id)
    )).scalar_one_or_none()
    if not node:
        return None
    if data.type is not None: node.node_type = data.type
    if data.name is not None: node.name = data.name
    if data.role is not None: node.role_label = data.role
    if data.status is not None: node.status = data.status
    if data.accent is not None: node.accent_color = data.accent
    if data.stat is not None: node.stat_label = data.stat
    if data.agent_id is not None: node.agent_id = data.agent_id
    if data.parent_id is not None: node.parent_id = _resolve_parent(data.parent_id, pm)
    if data.pos_x is not None: node.pos_x = data.pos_x
    if data.pos_y is not None: node.pos_y = data.pos_y
    await db.commit()
    await db.refresh(node)
    return _to_out(node, pm)


async def delete_node(db: AsyncSession, node_id: str, project_id: str) -> bool:
    node = (await db.execute(
        select(Node).where(Node.id == node_id, Node.project_id == project_id)
    )).scalar_one_or_none()
    if not node:
        return False
    # cascade reparent: 삭제 노드의 자식을 삭제 노드의 부모로 입양(고아 방지)
    children = (await db.execute(select(Node).where(Node.parent_id == node_id))).scalars().all()
    for child in children:
        child.parent_id = node.parent_id
    await db.delete(node)
    await db.commit()
    return True


async def update_position(db: AsyncSession, node_id: str, project_id: str,
                          pos_x: float, pos_y: float) -> NodeOut | None:
    pm = await _pm_id(db, project_id)
    node = (await db.execute(
        select(Node).where(Node.id == node_id, Node.project_id == project_id)
    )).scalar_one_or_none()
    if not node:
        return None
    node.pos_x, node.pos_y = pos_x, pos_y
    await db.commit()
    await db.refresh(node)
    return _to_out(node, pm)


async def seed_pm_node(db: AsyncSession, project_id: str) -> str:
    """PM 노드가 없으면 자동 생성(멱등). PM 노드 id 반환."""
    existing = await _pm_id(db, project_id)
    if existing:
        return existing
    node = Node(
        project_id=project_id, node_class="pm", node_type="ai", name="PM Agent",
        role_label="Project Manager", status="active", accent_color="#7c3aed", stat_label="online",
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node.id
