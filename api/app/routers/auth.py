"""
인증 라우터.

POST /api/auth/signup    — 이메일 회원가입 → JWT 발급
POST /api/auth/login     — 이메일 로그인 → JWT 발급
POST /api/auth/telegram  — Telegram Login Widget 결과 검증 → JWT 발급
GET  /api/auth/me        — 현재 사용자 정보 확인
GET  /api/auth/dev-token — Dev 전용 자동 로그인 JWT (DIPEEN_DEV_TOKEN 필요)
"""

import hashlib
import hmac
import os as _os
import re
import secrets
import time
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.db.models import User
from app.db.session import async_session

router = APIRouter()


def _hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 (stdlib, no C deps)."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations=600_000)
    return f"pbkdf2:sha256:600000${salt}${dk.hex()}"


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against PBKDF2-SHA256 hash."""
    try:
        _, salt, stored_hash = hashed.split("$", 2)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations=600_000)
        return secrets.compare_digest(dk.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False

_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
_REQUIRE_AUTH = _os.getenv("DIPEEN_REQUIRE_AUTH", "false").lower() == "true"
_DEV_TOKEN = _os.getenv("DIPEEN_DEV_TOKEN", "")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── JWT helpers ──────────────────────────────────────────────────

def _issue_user_jwt(user_id: str, team_id: str | None, role: str, name: str) -> str:
    """이메일 사용자용 JWT 발급."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "team_id": team_id or "default-team",
        "role": role,
        "name": name,
        "source": "email",
        "iat": now,
        "exp": now + 86400 * 30,  # 30일
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _issue_team_jwt(team_id: str, role: str = "member", display_name: str = "") -> str:
    """팀 기반 JWT 발급 (에이전트 / 기존 팀 플로우용)."""
    now = int(time.time())
    payload = {
        "team_id": team_id,
        "role": role,
        "name": display_name,
        "source": "dipeen",
        "iat": now,
        "exp": now + 86400 * 30,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _issue_jwt(user: dict) -> str:
    """Telegram 사용자용 JWT."""
    user_id = str(user["id"])
    payload = {
        "sub": user_id,
        "team_id": f"tg-{user_id}",
        "name": user.get("first_name", ""),
        "username": user.get("username", ""),
        "source": "telegram",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def _verify_telegram_auth(data: dict) -> bool:
    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(check_data.items())
    )
    secret_key = hashlib.sha256(_BOT_TOKEN.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return False
    auth_date = int(data.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        return False
    return True


# ── Request/Response models ───────────────────────────────────────

class SignupBody(BaseModel):
    email: str
    password: str
    name: str


class LoginBody(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    team_id: str | None
    role: str
    name: str


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    username: str | None


# ── Routes ────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignupBody):
    """이메일 회원가입."""
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email format")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if not body.name.strip():
        raise HTTPException(422, "Name is required")

    async with async_session() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Email already registered")

        user = User(
            email=email,
            password_hash=_hash_password(body.password),
            name=body.name.strip(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = _issue_user_jwt(user.id, user.team_id, user.role, user.name)
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        team_id=user.team_id,
        role=user.role,
        name=user.name,
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginBody):
    """이메일 로그인."""
    email = body.email.strip().lower()

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = _issue_user_jwt(user.id, user.team_id, user.role, user.name)
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        team_id=user.team_id,
        role=user.role,
        name=user.name,
    )


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(body: TelegramAuthData):
    """Telegram Login Widget 결과 검증 후 JWT 발급."""
    if not _BOT_TOKEN:
        raise HTTPException(503, "Telegram auth not configured")
    data = body.model_dump()
    if not _verify_telegram_auth(data):
        raise HTTPException(401, "Telegram auth hash invalid or expired")
    token = _issue_jwt(data)
    return TokenResponse(
        access_token=token,
        user_id=str(body.id),
        name=body.first_name,
        username=body.username,
    )


# ── Dependencies ──────────────────────────────────────────────────

def get_team_id(authorization: Annotated[str | None, Header()] = None) -> str:
    """JWT에서 team_id 추출. DIPEEN_REQUIRE_AUTH=true면 토큰 필수."""
    if not authorization or not authorization.startswith("Bearer "):
        if _REQUIRE_AUTH:
            raise HTTPException(401, "Authentication required")
        return "default-team"
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("team_id", "default-team")
    except jwt.InvalidTokenError:
        if _REQUIRE_AUTH:
            raise HTTPException(401, "Invalid token")
        return "default-team"


def get_role(authorization: Annotated[str | None, Header()] = None) -> str | None:
    """JWT에서 role 추출."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("role")
    except jwt.InvalidTokenError:
        return None


def require_owner(role: Annotated[str | None, Depends(get_role)] = None) -> None:
    """owner 역할이 아니면 403. None(soft auth)은 통과."""
    if role is not None and role != "owner":
        raise HTTPException(403, "Owner 권한 필요")


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    """JWT에서 사용자 정보 추출 (strict — 401 on missing)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authorization header missing")
    token = authorization.removeprefix("Bearer ")
    return _decode_jwt(token)


@router.get("/me")
async def me(authorization: Annotated[str | None, Header()] = None):
    """현재 로그인한 사용자 정보."""
    if not authorization or not authorization.startswith("Bearer "):
        return {"user_id": None, "team_id": None, "role": None, "name": None, "avatar_emoji": None}
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id") or payload.get("sub")
        result = {
            "user_id": user_id,
            "team_id": payload.get("team_id"),
            "role": payload.get("role"),
            "name": payload.get("name"),
            "avatar_emoji": None,
        }
        # user JWT면 DB에서 avatar_emoji 가져옴
        if payload.get("source") == "email" and user_id:
            async with async_session() as db:
                row = await db.execute(select(User).where(User.id == user_id))
                user = row.scalar_one_or_none()
                if user:
                    result["avatar_emoji"] = user.avatar_emoji
                    result["name"] = user.name
        return result
    except jwt.InvalidTokenError:
        return {"user_id": None, "team_id": None, "role": None, "name": None, "avatar_emoji": None}


@router.get("/dev-token")
async def dev_token():
    """개발 환경 자동 로그인용 더미 JWT 발급.
    DIPEEN_DEV_TOKEN 환경변수 미설정 시 404."""
    if not _DEV_TOKEN:
        raise HTTPException(404, "Dev mode not enabled")
    token = _issue_team_jwt("default-team", "owner", "Dev")
    return {"access_token": token, "token_type": "bearer"}
