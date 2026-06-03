import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update as sa_update

from app.config import settings
from app.db.models import Team
from app.db.session import engine, async_session, create_tables
from app.routers import tasks, agents
from app.routers import events, chat, usage, meeting, onboarding, auth, teams, graph, hermes, projects, decisions, control_plane, workspace

DEFAULT_TEAM_ID = "default-team"


HEARTBEAT_TIMEOUT_SEC = 60
WATCHDOG_INTERVAL_SEC = 30


async def _heartbeat_watchdog() -> None:
    """K-6: 60초 이상 heartbeat 없는 에이전트를 offline 처리하고
    in_progress 태스크를 pending으로 되돌림."""
    from app.db.models import Agent, Task

    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL_SEC)
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC)

            async with async_session() as db:
                stmt = select(Agent).where(
                    Agent.status.in_(["working", "idle"]),
                    Agent.last_heartbeat < cutoff,
                )
                result = await db.execute(stmt)
                stale_agents = result.scalars().all()

                for agent in stale_agents:
                    old_status = agent.status
                    old_task_id = agent.current_task_id

                    agent.status = "offline"
                    agent.current_task_id = None

                    if old_task_id:
                        await db.execute(
                            sa_update(Task)
                            .where(Task.task_id == old_task_id, Task.status == "in_progress")
                            .values(
                                status="pending",
                                assigned_agent_id=None,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                        await events.broadcast({
                            "type": "task_update",
                            "task_id": old_task_id,
                            "status": "pending",
                            "agent_id": None,
                            "reason": "agent_offline",
                        })

                    await events.broadcast({
                        "type": "agent_status",
                        "agent_id": agent.agent_id,
                        "status": "offline",
                        "current_task_id": None,
                        "reason": "heartbeat_timeout",
                    })
                    print(
                        f"[watchdog] {agent.agent_id} → offline "
                        f"(was {old_status}, task={old_task_id})",
                        flush=True,
                    )

                if stale_agents:
                    await db.commit()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[watchdog] 오류 (무시): {e}", flush=True)


async def _ensure_default_team() -> None:
    async with async_session() as db:
        result = await db.execute(select(Team).where(Team.id == DEFAULT_TEAM_ID))
        if not result.scalar_one_or_none():
            db.add(Team(id=DEFAULT_TEAM_ID, name="Default Team"))
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import validate_production_settings
    validate_production_settings(settings)
    await create_tables()
    await _ensure_default_team()
    await events._init_redis()

    # K-6: heartbeat watchdog
    watchdog = asyncio.create_task(_heartbeat_watchdog())

    yield

    watchdog.cancel()
    try:
        await watchdog
    except asyncio.CancelledError:
        pass

    await events._close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — VPN 내부 + 로컬 개발 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(usage.router, prefix="/api/usage", tags=["usage"])
app.include_router(events.router, tags=["events"])
app.include_router(meeting.router, prefix="/api/meeting", tags=["meeting"])
app.include_router(onboarding.router, prefix="/api/onboarding", tags=["onboarding"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(hermes.router, tags=["hermes"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["decisions"])
app.include_router(control_plane.router, prefix="/api", tags=["control-plane"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
