"""프로젝트 그래프 노드 스키마 (Leekuejea ProjectAgent 흡수, dipeen async 포팅).

응답 필드는 기존 `/api/graph/nodes`(GraphNode) + 프론트 `lib/api.ts` GraphNode 타입과 일치시킨다
(type/role/accent/stat) — 그래야 React Flow 그래프가 두 소스(파생 vs 영속)를 같은 모양으로 소비.
"""
from __future__ import annotations

from pydantic import BaseModel


class NodeCreate(BaseModel):
    name: str
    type: str = "ai"              # ai | human
    role: str = ""               # role_label (FE/BE/QA/PM…)
    status: str = "standby"
    accent: str = "#38bdf8"
    stat: str = ""
    parent_id: str | None = None  # "pm" 별칭 또는 노드 id
    agent_id: str | None = None   # 실제 Agent 연결
    pos_x: float = 0.0
    pos_y: float = 0.0


class NodeUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    role: str | None = None
    status: str | None = None
    accent: str | None = None
    stat: str | None = None
    parent_id: str | None = None
    agent_id: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class NodeOut(BaseModel):
    id: str
    project_id: str
    parent_id: str | None        # PM 노드면 "pm" 별칭으로 반환
    agent_id: str | None
    node_class: str              # pm | agent
    type: str
    name: str
    role: str
    status: str
    accent: str
    stat: str
    pos_x: float
    pos_y: float
