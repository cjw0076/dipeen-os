"""node_service — Leekuejea ProjectAgent 흡수분의 핵심 로직 검증(async 포팅).

self-contained: in-memory SQLite(StaticPool로 연결 간 공유) + Base.metadata.create_all.
검증: seed_pm_node 멱등 · "pm" 부모 별칭 · 삭제 시 cascade reparent(고아 방지).
"""
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.schemas.node import NodeCreate
from app.services import node_service


def _sessionmaker():
    async def build():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return async_sessionmaker(engine, expire_on_commit=False)
    return asyncio.run(build())


def _run(coro_fn):
    Session = _sessionmaker()

    async def wrapper():
        async with Session() as db:
            return await coro_fn(db)
    return asyncio.run(wrapper())


def test_seed_pm_idempotent():
    async def body(db):
        pid = await node_service.seed_pm_node(db, "P1")
        pid2 = await node_service.seed_pm_node(db, "P1")
        assert pid == pid2                       # 멱등 — 두 번째는 기존 반환
        nodes = await node_service.list_nodes(db, "P1")
        assert len(nodes) == 1
        assert nodes[0].node_class == "pm"
    _run(body)


def test_create_returns_pm_alias():
    async def body(db):
        await node_service.seed_pm_node(db, "P1")
        n = await node_service.create_node(db, "P1", NodeCreate(name="FE", role="FE", parent_id="pm"))
        assert n.node_class == "agent"
        assert n.parent_id == "pm"               # 부모가 PM이면 별칭으로 반환
        assert n.type == "ai" and n.role == "FE"
    _run(body)


def test_delete_cascade_reparent():
    async def body(db):
        await node_service.seed_pm_node(db, "P1")
        parent = await node_service.create_node(db, "P1", NodeCreate(name="lead"))   # parent→pm
        child = await node_service.create_node(db, "P1", NodeCreate(name="sub", parent_id=parent.id))
        assert child.parent_id == parent.id
        ok = await node_service.delete_node(db, parent.id, "P1")
        assert ok
        nodes = await node_service.list_nodes(db, "P1")
        ids = {n.id for n in nodes}
        assert parent.id not in ids              # 삭제됨
        child_after = next(n for n in nodes if n.id == child.id)
        assert child_after.parent_id == "pm"     # 부모의 부모(pm)로 입양 — 고아 안 됨
    _run(body)


def test_scoped_by_project():
    async def body(db):
        await node_service.seed_pm_node(db, "P1")
        await node_service.seed_pm_node(db, "P2")
        await node_service.create_node(db, "P1", NodeCreate(name="onlyP1"))
        assert len(await node_service.list_nodes(db, "P1")) == 2   # pm + onlyP1
        assert len(await node_service.list_nodes(db, "P2")) == 1   # pm만
    _run(body)
