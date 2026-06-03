"""
팀 온보딩 라우터 (L-1 + U-1).

POST /api/teams              — 팀 생성 + owner JWT 발급
GET  /api/teams/{team_id}    — 팀 정보 조회
POST /api/teams/{team_id}/invite  — 초대 코드 생성 (1회용, 24h TTL, DB 영속)
GET  /api/teams/join?code=   — 초대 코드로 팀 합류 + member JWT 발급
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from app.db.models import Team, Agent, User, InviteCode
from app.db.session import async_session
from app.routers.auth import _issue_team_jwt, _issue_user_jwt, get_team_id, get_current_user

router = APIRouter()

INVITE_TTL_SEC = 86400  # 24시간


# ── Request/Response models ───────────────────────────────────────

class CreateTeamBody(BaseModel):
    name: str


class CreateTeamResponse(BaseModel):
    team_id: str
    name: str
    token: str


class TeamInfoResponse(BaseModel):
    team_id: str
    name: str
    created_at: str
    agent_count: int


class InviteResponse(BaseModel):
    code: str
    expires_at: str
    join_url: str


class JoinResponse(BaseModel):
    team_id: str
    token: str


# ── Routes ────────────────────────────────────────────────────────

@router.post("", response_model=CreateTeamResponse)
async def create_team(
    body: CreateTeamBody,
    authorization: Annotated[str | None, Header()] = None,
):
    """팀 생성 + owner JWT 발급. 인증된 유저면 team_id 연동."""
    if not body.name.strip():
        raise HTTPException(400, "Team name cannot be empty")

    # 인증된 유저 확인 (선택적)
    user_payload = None
    try:
        user_payload = get_current_user(authorization)
    except HTTPException:
        pass

    async with async_session() as db:
        team = Team(name=body.name.strip())
        db.add(team)
        await db.flush()

        # 인증된 유저면 해당 유저를 team owner로 설정
        if user_payload and user_payload.get("user_id"):
            result = await db.execute(
                select(User).where(User.id == user_payload["user_id"])
            )
            user = result.scalar_one_or_none()
            if user:
                user.team_id = team.id
                user.role = "owner"

        await db.commit()
        await db.refresh(team)

    # 유저가 있으면 user JWT 재발급 (team_id 포함), 아니면 team JWT
    if user_payload and user_payload.get("user_id"):
        token = _issue_user_jwt(
            user_payload["user_id"], team.id, "owner",
            user_payload.get("name", body.name.strip()),
        )
    else:
        token = _issue_team_jwt(team.id, role="owner", display_name=body.name.strip())

    return CreateTeamResponse(team_id=team.id, name=team.name, token=token)


@router.get("/join", response_model=JoinResponse)
async def join_team(code: str, authorization: Annotated[str | None, str] = None):
    """초대 코드로 팀 합류 + member JWT 발급 (1회용, DB 영속)."""
    now = datetime.now(timezone.utc)

    async with async_session() as db:
        result = await db.execute(
            select(InviteCode).where(
                InviteCode.code == code,
                InviteCode.used == False,
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise HTTPException(404, "Invalid invite code")
        if invite.expires_at.replace(tzinfo=timezone.utc) < now:
            invite.used = True
            await db.commit()
            raise HTTPException(410, "Invite code expired")

        team_id = invite.team_id
        invite.used = True

        # 팀 존재 확인
        team_result = await db.execute(select(Team).where(Team.id == team_id))
        team = team_result.scalar_one_or_none()
        if not team:
            await db.commit()
            raise HTTPException(404, "Team not found")

        # 인증된 유저면 team_id 연동
        user_payload = None
        try:
            user_payload = get_current_user(authorization)
        except HTTPException:
            pass

        if user_payload and user_payload.get("user_id"):
            user_result = await db.execute(
                select(User).where(User.id == user_payload["user_id"])
            )
            user = user_result.scalar_one_or_none()
            if user:
                user.team_id = team_id
                user.role = "member"

        await db.commit()

    # 유저가 있으면 user JWT, 아니면 team JWT
    if user_payload and user_payload.get("user_id"):
        token = _issue_user_jwt(
            user_payload["user_id"], team_id, "member",
            user_payload.get("name", ""),
        )
    else:
        token = _issue_team_jwt(team_id, role="member")

    return JoinResponse(team_id=team_id, token=token)


@router.get("/{team_id}", response_model=TeamInfoResponse)
async def get_team(
    team_id: str,
    caller_team_id: Annotated[str, Depends(get_team_id)],
):
    """팀 정보 조회 (소속 팀만 조회 가능)."""
    if caller_team_id != "default-team" and caller_team_id != team_id:
        raise HTTPException(403, "Access denied")

    async with async_session() as db:
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            raise HTTPException(404, "Team not found")

        count_result = await db.execute(
            select(func.count()).select_from(Agent).where(Agent.team_id == team_id)
        )
        agent_count = count_result.scalar() or 0

    return TeamInfoResponse(
        team_id=team.id,
        name=team.name,
        created_at=team.created_at.isoformat(),
        agent_count=agent_count,
    )


@router.post("/{team_id}/invite", response_model=InviteResponse)
async def create_invite(
    team_id: str,
    caller_team_id: Annotated[str, Depends(get_team_id)],
):
    """초대 코드 생성 (DB 영속, 1회용, 24h TTL)."""
    if caller_team_id != "default-team" and caller_team_id != team_id:
        raise HTTPException(403, "Access denied")

    async with async_session() as db:
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            raise HTTPException(404, "Team not found")

        code = secrets.token_urlsafe(6)[:8].upper()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_TTL_SEC)

        invite = InviteCode(code=code, team_id=team_id, expires_at=expires_at)
        db.add(invite)
        await db.commit()

    return InviteResponse(
        code=code,
        expires_at=expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        join_url=f"/onboarding?code={code}",
    )
