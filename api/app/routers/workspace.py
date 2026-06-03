"""Workspace Spec API — host가 만든 TeamWorkspaceSpec을 web UI가 렌더하도록 노출.

**web UI는 스스로 판단하지 않는다** — 이 API의 spec을 렌더만 한다. mode를 바꾸면(`POST /apply`) 화면이 달라진다.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.nat.core import workspace_spec

router = APIRouter()
_MODES = ("public_demo", "team", "production", "debug")


def _root() -> str:
    # host HQ의 작업공간 루트. DIPEEN_WORKSPACE_ROOT > NAT_WORKSPACE > cwd.
    return os.getenv("DIPEEN_WORKSPACE_ROOT") or os.getenv("NAT_WORKSPACE") or "."


@router.get("/spec")
async def get_spec():
    """현재 workspace spec. 없으면 team 기본으로 폴백(web UI가 항상 렌더할 게 있게)."""
    spec = workspace_spec.load_spec(_root()) or workspace_spec.default_spec("team", workspace_id="default")
    return spec.model_dump(mode="json")


class ApplyBody(BaseModel):
    mode: str = "team"                             # public_demo | team | production | debug
    workspace_id: str = "default"


@router.post("/apply")
async def apply(body: ApplyBody):
    """mode 적용 → spec 저장(.dipeen/workspace.yaml). 이후 web UI는 새 spec(panels)을 렌더한다."""
    normalized = body.mode.replace("-", "_")
    mode = normalized if normalized in _MODES else "team"
    spec = workspace_spec.default_spec(mode, workspace_id=body.workspace_id)  # type: ignore[arg-type]
    workspace_spec.save_spec(spec, _root())
    return spec.model_dump(mode="json")
