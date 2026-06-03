from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    key: str | None = None
    description: str | None = None
    repository_url: str | None = None
    default_branch: str = "main"
    room_id: str | None = None
    metadata: dict | None = None


class ProjectBootstrap(BaseModel):
    team_name: str = "Dipeen Team"
    project_name: str = "Dipeen Launch"
    repository_url: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    description: str | None = None
    repository_url: str | None = None
    default_branch: str | None = None
    metadata: dict | None = None


class ProjectOut(BaseModel):
    id: str
    team_id: str
    name: str
    key: str
    slug: str
    status: str
    description: str | None
    repository_url: str | None
    default_branch: str
    room_id: str
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
