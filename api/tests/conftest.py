import os
import pathlib
import tempfile

# 앱 import 전에 테스트 DB/시크릿 환경을 고정한다 (config는 import 시점에 읽힘).
_TMPDIR = tempfile.mkdtemp(prefix="dipeen-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{pathlib.Path(_TMPDIR, 'test.db').as_posix()}"
os.environ["DIPEEN_SECRET_KEY"] = "test-secret-key"
os.environ["DIPEEN_DEBUG"] = "true"          # get_team_id soft-auth → default-team
os.environ.pop("REDIS_URL", None)            # in-process broadcast fallback

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    # lifespan이 ASGITransport에선 자동 실행되지 않으므로, lifespan이 하는 일을 직접 수행한다.
    from app.db.session import create_tables, engine
    from app.db.models import Base
    from app import main as app_main

    # 테스트 격리: 공유 sqlite 파일 상태가 테스트 간에 누수되지 않도록 매 테스트를
    # 깨끗한 스키마로 시작한다 (한 테스트가 만든 행이 다른 테스트의 가정을 깨지 않게).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_tables()
    await app_main._ensure_default_team()    # default-team Team row 시드 (FK 충족)

    transport = ASGITransport(app=app_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _isolate_nat_workspace(tmp_path, monkeypatch):
    """모든 테스트의 NAT 저장소(control_plane_root=NAT_WORKSPACE)를 per-test temp로 격리.

    control_plane_root()는 NAT_WORKSPACE 미설정 시 repo의 `nat-workspace/`(공유·stale)를 봐서 테스트 간
    state가 누수된다(test_pm_loop_default_dispatch_is_proposal_only flaky의 뿌리). 이걸 끊는다 — 명시적으로
    NAT_WORKSPACE를 설정하는 테스트는 그 값이 우선(body monkeypatch가 fixture보다 뒤).
    """
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "_nat_ws"))
