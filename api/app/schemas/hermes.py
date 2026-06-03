from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

HermesMessageType = Literal[
    "NODE_HELLO",
    "NODE_READY",
    "NODE_BYE",
    "PRESENCE_UPDATE",
    "TASK_ASSIGN",
    "TASK_ACK",
    "TASK_PROGRESS",
    "TASK_RESULT",
    "LOG_STREAM",
    "A2A_MSG",
    "MEETING_EVENT",
    "MEMORY_EVENT",
    "ERROR"
]

class HermesLogPayload(BaseModel):
    level: str = "info"
    text: str
    changed_files: List[str] = Field(default_factory=list)
    tests: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=datetime.utcnow)

class HermesA2APayload(BaseModel):
    to_agent_id: str
    content: Any
    message_type: str = "message"  # message, call, response, event
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class HermesEnvelope(BaseModel):
    v: int = Field(default=1, description="Protocol version")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique message ID / Idempotency key")
    type: HermesMessageType
    team_id: str
    room_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None
    reply_to: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
