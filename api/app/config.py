import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "dipeen-api"
    debug: bool = False

    # SQLite DB — 로컬/개발용 (PostgreSQL 미설정 시 사용)
    db_path: Path = Path(__file__).parent.parent / "dipeen.db"

    # API 서버 바인드
    host: str = "0.0.0.0"
    port: int = 8000

    # long-polling 대기 시간 (초)
    poll_timeout: int = 30

    # JWT 시크릿 — 프로덕션에서 반드시 변경
    secret_key: str = "change-me-in-production"

    # CORS — 콤마 구분 Origins ("*" = 모두 허용)
    cors_origins: str = "*"

    # 공유 컨텍스트 디렉토리 (WORKSPACE.md 저장 위치)
    shared_dir: Path = Path(__file__).parent.parent.parent / "dipeen-shared"

    @property
    def database_url(self) -> str:
        # DATABASE_URL 환경변수 우선 (PostgreSQL 등)
        override = os.getenv("DATABASE_URL", "")
        if override:
            # asyncpg 드라이버로 변환 (postgres:// → postgresql+asyncpg://)
            if override.startswith("postgres://"):
                override = override.replace("postgres://", "postgresql+asyncpg://", 1)
            elif override.startswith("postgresql://") and "+asyncpg" not in override:
                override = override.replace("postgresql://", "postgresql+asyncpg://", 1)
            return override
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def redis_url(self) -> str | None:
        return os.getenv("REDIS_URL") or None

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url

    model_config = {"env_prefix": "DIPEEN_"}


settings = Settings()


PLACEHOLDER_SECRET = "change-me-in-production"


def validate_production_settings(s: "Settings") -> None:
    """프로덕션에서 안전하지 않은 기본값으로 기동하는 것을 거부한다 (debug=True면 통과)."""
    if s.debug:
        return
    problems = []
    if s.secret_key == PLACEHOLDER_SECRET:
        problems.append("DIPEEN_SECRET_KEY is the default placeholder")
    if str(s.cors_origins).strip() == "*":
        problems.append("DIPEEN_CORS_ORIGINS is '*' (wildcard) in production")
    if problems:
        raise RuntimeError("Insecure production config: " + "; ".join(problems))
