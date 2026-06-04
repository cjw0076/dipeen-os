"""dipeen open — deterministic, dependency-injected cold-boot + workspace orchestration.

Core logic does NO real subprocess / network. The CLI edge injects real boot/tunnel/http.
Boot policy (load-bearing): uvicorn fallback ONLY when Docker is absent or forced; a
Docker-present failure raises a clear error — never a silent uvicorn fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

BootMode = Literal["auto", "uvicorn"]


@dataclass
class BootDeps:
    hq_health: Callable[[], bool]
    docker_available: Callable[[], bool]
    boot_docker: Callable[[], tuple[bool, str]]      # (ok, error_detail)
    boot_uvicorn: Callable[[], tuple[bool, str]]


@dataclass
class EnsureHqResult:
    hq_started_by_us: bool


class EnsureHqError(RuntimeError):
    """Human-language boot failure (the message is shown as-is)."""
    def __init__(self, human: str, detail: str = ""):
        super().__init__(human)
        self.human = human
        self.detail = detail


def ensure_hq(*, mode: BootMode, deps: BootDeps,
              health_retries: int = 30, health_interval: float = 1.0,
              sleep: Optional[Callable[[float], None]] = None) -> EnsureHqResult:
    if deps.hq_health():
        return EnsureHqResult(hq_started_by_us=False)
    import time
    _sleep = sleep or time.sleep
    if mode == "uvicorn" or not deps.docker_available():
        ok, detail = deps.boot_uvicorn()
        if not ok:
            raise EnsureHqError("Couldn't start the local Dipeen API.", detail)
    else:
        ok, detail = deps.boot_docker()
        if not ok:
            raise EnsureHqError(
                f"Couldn't start the Dipeen API with Docker.\nReason: {detail}\n\n"
                "Try:\n  docker compose down\n  docker compose up -d", detail)
    for _ in range(health_retries):
        if deps.hq_health():
            return EnsureHqResult(hq_started_by_us=True)
        _sleep(health_interval)
    raise EnsureHqError("Couldn't start the Dipeen API. Is Docker running?")


@dataclass
class SessionDeps:
    ensure_team: Callable[[Optional[str]], dict]     # name -> {"id","name"}
    mint_invite: Callable[[str], dict]               # team_id -> {"code","expires_at"}


@dataclass
class OpenSessionResult:
    team_name: str
    invite_code: str
    invite_expires_at: str
    api_url: str
    web_url: str                 # already includes ?api=
    join_command: str
    slash_join_command: str
    hq_started_by_us: bool = False


def open_workspace(*, team: Optional[str], api_url: str, web_url: str,
                   deps: SessionDeps, hq_started_by_us: bool = False) -> OpenSessionResult:
    t = deps.ensure_team(team)
    inv = deps.mint_invite(t["id"])
    code = inv["code"]
    return OpenSessionResult(
        team_name=t["name"], invite_code=code, invite_expires_at=inv["expires_at"],
        api_url=api_url, web_url=f"{web_url}?api={api_url}",
        join_command=f"dipeen-agent join {code} --api-url {api_url}",
        slash_join_command=f"/dipeen join {code}",
        hq_started_by_us=hq_started_by_us)
