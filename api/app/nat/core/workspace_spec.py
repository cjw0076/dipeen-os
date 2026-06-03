"""TeamWorkspaceSpec (host CLI ↔ web UI) — **host가 spec을 만들고 web UI는 렌더만 한다.**

web UI는 고정 앱이 아니라 TeamWorkspaceSpec을 렌더링하는 shell. mode(public_demo/team/production/debug)에
따라 패널 구성·정책이 달라진다. UI 코드 수정 없이 `.dipeen/workspace.yaml`만 바꿔 화면이 달라진다.

provider는 전부 **CLI 래퍼**(claude/codex/omo/hermes=local_cli/experimental) + fake — Dipeen은 키를 안 가짐.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

WorkspaceMode = Literal["public_demo", "team", "production", "debug"]

# 모드 → 패널. web UI는 이 목록을 렌더만 한다(스스로 판단 안 함).
_PANELS: dict[str, list[str]] = {
    "public_demo": ["join_panel", "demo_panel", "meeting_room", "worker_status",
                    "routing_preview", "task_board", "run_timeline", "artifact_board",
                    "permission_inbox", "goal_progress", "system_health", "provider_status",
                    "recent_discussions"],
    "team":        ["meeting_room", "task_board", "worker_status", "routing_preview",
                    "run_timeline", "artifact_board", "permission_inbox", "memory_queue",
                    "goal_progress", "provider_status", "recent_discussions"],
    "production":  ["meeting_room", "task_board", "worker_status", "routing_preview",
                    "run_timeline", "artifact_board", "permission_inbox", "failure_inbox",
                    "memory_queue", "goal_progress", "system_health", "active_runs",
                    "provider_status", "recent_discussions"],
    "debug":       ["task_board", "worker_status", "command_queue", "event_log",
                    "run_timeline", "artifact_board", "permission_inbox", "provider_inspect",
                    "system_health", "active_runs"],
}

_DEFAULT_POLICIES = {
    "permission_executor_mode": "dry_run",        # 안전 기본 — 진짜 PR/push/deploy 없음
    "github.pr.create": "requires_approval",
    "deploy.production": "denied",
    "secret.read": "denied",
}

# provider = CLI 래퍼(키 아님). omo/hermes는 어댑터 미완 → experimental.
_DEFAULT_PROVIDERS = {"claude": "local_cli", "codex": "local_cli", "fake": "local_cli",
                      "omo": "experimental", "hermes": "experimental"}


class WorkspaceUI(BaseModel):
    layout: str = "control_tower"
    panels: list[str] = Field(default_factory=list)
    show_dry_run_banner: bool = True


class WorkspaceRepo(BaseModel):
    id: str                                        # repo.ezmap-web
    workspace_ref: str                             # workspace://ezmap-web


class WorkspaceProject(BaseModel):
    repos: list[WorkspaceRepo] = Field(default_factory=list)


class WorkspaceTeam(BaseModel):
    roles: list[str] = Field(default_factory=list)


class TeamWorkspaceSpec(BaseModel):
    """host CLI가 만드는 팀 작업공간 명세. web UI의 single source of truth."""
    workspace_id: str
    mode: WorkspaceMode = "team"
    ui: WorkspaceUI = Field(default_factory=WorkspaceUI)
    project: WorkspaceProject = Field(default_factory=WorkspaceProject)
    team: WorkspaceTeam = Field(default_factory=WorkspaceTeam)
    policies: dict[str, str] = Field(default_factory=dict)
    providers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_top_level_sections(cls, data: Any) -> Any:
        """Old specs used top-level repos/roles. Keep loading them, but never write them."""
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy_repos = migrated.pop("repos", None)
        legacy_roles = migrated.pop("roles", None)
        if "project" not in migrated:
            migrated["project"] = {"repos": legacy_repos or []}
        if "team" not in migrated:
            migrated["team"] = {"roles": legacy_roles or []}
        return migrated


def default_spec(mode: WorkspaceMode, *, workspace_id: str) -> TeamWorkspaceSpec:
    """mode → 기본 spec(패널·정책·provider). host CLI `dipeen workspace init --mode <mode>`가 사용."""
    panels = list(_PANELS.get(mode, _PANELS["team"]))
    return TeamWorkspaceSpec(
        workspace_id=workspace_id, mode=mode,
        ui=WorkspaceUI(panels=panels, show_dry_run_banner=True),
        project=WorkspaceProject(),
        team=WorkspaceTeam(roles=["frontend", "backend", "qa", "memory"]),
        policies=dict(_DEFAULT_POLICIES),
        providers=dict(_DEFAULT_PROVIDERS))


def _spec_path(root: str | Path) -> Path:
    return Path(root) / ".dipeen" / "workspace.yaml"


def save_spec(spec: TeamWorkspaceSpec, root: str | Path = ".") -> Path:
    """spec → .dipeen/workspace.yaml(사람이 읽고 편집 가능)."""
    p = _spec_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(spec.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    return p


def load_spec(root: str | Path = ".") -> Optional[TeamWorkspaceSpec]:
    """.dipeen/workspace.yaml → spec. 없으면 None(정직한 부재 — UI는 기본 모드로 폴백)."""
    p = _spec_path(root)
    if not p.exists():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return TeamWorkspaceSpec.model_validate(data) if data else None
