import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, Team, ProjectMember
from app.db.session import async_session
from app.routers.auth import get_team_id
from app.routers.events import broadcast
from app.schemas.project import ProjectBootstrap, ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.node import NodeCreate, NodeUpdate
from app.services import node_service

router = APIRouter()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "project"


def _project_key(name: str, key: str | None = None) -> str:
    raw = (key or "").strip() or "".join(word[:1] for word in re.findall(r"[a-zA-Z0-9]+", name))
    raw = re.sub(r"[^a-zA-Z0-9]", "", raw).upper()
    return (raw or "PRJ")[:24]


async def _unique_slug(team_id: str, name: str) -> str:
    base = _slugify(name)
    slug = base
    suffix = 2
    async with async_session() as db:
        while True:
            row = await db.execute(select(Project).where(Project.team_id == team_id, Project.slug == slug))
            if not row.scalar_one_or_none():
                return slug
            slug = f"{base}-{suffix}"
            suffix += 1


async def _create_project(team_id: str, body: ProjectCreate) -> Project:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name cannot be empty")

    slug = await _unique_slug(team_id, name)
    project = Project(
        team_id=team_id,
        name=name,
        key=_project_key(name, body.key),
        slug=slug,
        status="planning",
        description=body.description,
        repository_url=body.repository_url,
        default_branch=body.default_branch or "main",
        room_id=body.room_id or slug,
        metadata_json=body.metadata or {},
    )

    async with async_session() as db:
        team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
        if not team:
            db.add(Team(id=team_id, name="Default Team" if team_id == "default-team" else "Dipeen Team"))
            await db.flush()
        db.add(project)
        await db.commit()
        await db.refresh(project)

    await broadcast({
        "type": "project_update",
        "project_id": project.id,
        "team_id": team_id,
        "status": project.status,
        "name": project.name,
        "room_id": project.room_id,
    })
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        rows = await db.execute(
            select(Project).where(Project.team_id == team_id).order_by(Project.created_at.desc())
        )
        return list(rows.scalars().all())


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, team_id: str = Depends(get_team_id)):
    return await _create_project(team_id, body)


@router.post("/bootstrap", response_model=ProjectOut)
async def bootstrap_project(body: ProjectBootstrap, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
        if not team:
            team = Team(id=team_id, name=body.team_name.strip() or "Dipeen Team")
            db.add(team)
        elif body.team_name.strip() and team.name in {"Default Team", "Dipeen Team"}:
            team.name = body.team_name.strip()

        existing = (
            await db.execute(
                select(Project).where(Project.team_id == team_id).order_by(Project.created_at.desc())
            )
        ).scalars().first()
        if existing:
            if body.repository_url and not existing.repository_url:
                existing.repository_url = body.repository_url
            if body.description and not existing.description:
                existing.description = body.description
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing)
            return existing

    return await _create_project(
        team_id,
        ProjectCreate(
            name=body.project_name,
            description=body.description,
            repository_url=body.repository_url,
        ),
    )


@router.get("/current", response_model=ProjectOut | None)
async def current_project(team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        return (
            await db.execute(
                select(Project).where(Project.team_id == team_id).order_by(Project.created_at.desc())
            )
        ).scalars().first()


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_id, Project.team_id == team_id))
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "Project not found")
        return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectUpdate, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_id, Project.team_id == team_id))
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "Project not found")

        if body.name is not None and body.name.strip():
            project.name = body.name.strip()
        if body.status is not None:
            project.status = body.status
        if body.description is not None:
            project.description = body.description
        if body.repository_url is not None:
            project.repository_url = body.repository_url
        if body.default_branch is not None and body.default_branch.strip():
            project.default_branch = body.default_branch.strip()
        if body.metadata is not None:
            project.metadata_json = {**(project.metadata_json or {}), **body.metadata}

        project.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(project)

    await broadcast({
        "type": "project_update",
        "project_id": project.id,
        "team_id": team_id,
        "status": project.status,
        "name": project.name,
        "room_id": project.room_id,
    })
    return project


# ════════ 프로젝트 그래프 노드 (Leekuejea ProjectAgent 흡수) ════════
# 영속 조직 그래프(PM/에이전트/사람) + 위치/계층. agents.metadata_json 기반 /api/graph/nodes와
# 달리 프로젝트 단위로 영속. node_service가 로직(pm 별칭·cascade reparent·seed).

async def _scoped_project(db: AsyncSession, project_id: str, team_id: str) -> Project:
    p = (await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "project not found")
    return p


class Position(BaseModel):
    pos_x: float
    pos_y: float


@router.get("/{project_id}/nodes")
async def get_project_nodes(project_id: str, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        await node_service.seed_pm_node(db, project_id)   # PM 노드 멱등 보장(그래프 중심)
        return await node_service.graph(db, project_id)


@router.post("/{project_id}/nodes")
async def create_project_node(project_id: str, body: NodeCreate, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        await node_service.seed_pm_node(db, project_id)
        out = await node_service.create_node(db, project_id, body)
    await broadcast({"type": "node_created", "project_id": project_id, "node_id": out.id})
    return out


@router.patch("/{project_id}/nodes/{node_id}")
async def update_project_node(project_id: str, node_id: str, body: NodeUpdate,
                              team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        out = await node_service.update_node(db, node_id, project_id, body)
    if out is None:
        raise HTTPException(404, "node not found")
    return out


@router.delete("/{project_id}/nodes/{node_id}")
async def delete_project_node(project_id: str, node_id: str, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        ok = await node_service.delete_node(db, node_id, project_id)
    if not ok:
        raise HTTPException(404, "node not found")
    return {"ok": True, "node_id": node_id}


@router.patch("/{project_id}/nodes/{node_id}/position")
async def set_project_node_position(project_id: str, node_id: str, pos: Position,
                                    team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        out = await node_service.update_position(db, node_id, project_id, pos.pos_x, pos.pos_y)
    if out is None:
        raise HTTPException(404, "node not found")
    await broadcast({"type": "node_moved", "node_id": node_id, "pos_x": pos.pos_x, "pos_y": pos.pos_y})
    return out


# ════════ 프로젝트 멤버 (owner/editor/viewer · pending/active) ════════

class MemberIn(BaseModel):
    email: str | None = None
    user_id: str | None = None
    role: str = "viewer"       # owner | editor | viewer


class MemberPatch(BaseModel):
    role: str | None = None
    status: str | None = None  # pending | active


def _member_out(m: ProjectMember) -> dict:
    return {"id": m.id, "project_id": m.project_id, "user_id": m.user_id, "email": m.email,
            "role": m.role, "status": m.status,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None}


@router.get("/{project_id}/members")
async def list_project_members(project_id: str, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        rows = (await db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )).scalars().all()
    return [_member_out(m) for m in rows]


@router.post("/{project_id}/members")
async def add_project_member(project_id: str, body: MemberIn, team_id: str = Depends(get_team_id)):
    if not body.email and not body.user_id:
        raise HTTPException(400, "email or user_id required")
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        m = ProjectMember(project_id=project_id, email=body.email, user_id=body.user_id,
                          role=body.role, status="pending")
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return _member_out(m)


@router.patch("/{project_id}/members/{member_id}")
async def update_project_member(project_id: str, member_id: str, body: MemberPatch,
                                team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        m = (await db.execute(
            select(ProjectMember).where(ProjectMember.id == member_id,
                                        ProjectMember.project_id == project_id)
        )).scalar_one_or_none()
        if m is None:
            raise HTTPException(404, "member not found")
        if body.role is not None:
            m.role = body.role
        if body.status is not None:
            m.status = body.status
            if body.status == "active" and m.joined_at is None:
                m.joined_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(m)
        return _member_out(m)


@router.delete("/{project_id}/members/{member_id}")
async def remove_project_member(project_id: str, member_id: str, team_id: str = Depends(get_team_id)):
    async with async_session() as db:
        await _scoped_project(db, project_id, team_id)
        m = (await db.execute(
            select(ProjectMember).where(ProjectMember.id == member_id,
                                        ProjectMember.project_id == project_id)
        )).scalar_one_or_none()
        if m is None:
            raise HTTPException(404, "member not found")
        await db.delete(m)
        await db.commit()
    return {"ok": True, "member_id": member_id}
