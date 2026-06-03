from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
from datetime import datetime
import json
import logging
from app.schemas.hermes import HermesEnvelope

logger = logging.getLogger(__name__)

class NodeSession:
    def __init__(self, agent_id: str, team_id: str, websocket: WebSocket):
        self.agent_id = agent_id
        self.team_id = team_id
        self.websocket = websocket
        self.status = "connected"
        self.last_seen = datetime.utcnow()
        self.current_task_id: Optional[str] = None
        self.capabilities: Dict[str, Any] = {}

class HermesRegistry:
    def __init__(self):
        # agent_id -> NodeSession
        self.agent_sessions: Dict[str, NodeSession] = {}
        # team_id -> Set[WebSocket] for UI subscribers
        self.ui_subscribers: Dict[str, Set[WebSocket]] = {}

    async def register_agent(self, agent_id: str, team_id: str, websocket: WebSocket):
        session = NodeSession(agent_id, team_id, websocket)
        self.agent_sessions[agent_id] = session
        logger.info(f"Agent {agent_id} registered to team {team_id} via Hermes")
        await self.broadcast_presence(team_id, agent_id, "online")

    async def unregister_agent(self, agent_id: str):
        if agent_id in self.agent_sessions:
            session = self.agent_sessions[agent_id]
            team_id = session.team_id
            del self.agent_sessions[agent_id]
            logger.info(f"Agent {agent_id} unregistered from Hermes")
            await self.broadcast_presence(team_id, agent_id, "offline")

    async def subscribe_ui(self, team_id: str, websocket: WebSocket):
        if team_id not in self.ui_subscribers:
            self.ui_subscribers[team_id] = set()
        self.ui_subscribers[team_id].add(websocket)
        logger.info(f"UI subscriber added for team {team_id}")
        
        # Send current online status of all agents in this team to the new subscriber
        for session in self.agent_sessions.values():
            if session.team_id == team_id:
                await self.send_to_websocket(websocket, HermesEnvelope(
                    type="PRESENCE_UPDATE",
                    team_id=team_id,
                    agent_id=session.agent_id,
                    payload={"status": "online", "capabilities": session.capabilities}
                ))

    async def unsubscribe_ui(self, team_id: str, websocket: WebSocket):
        if team_id in self.ui_subscribers:
            self.ui_subscribers[team_id].discard(websocket)
            if not self.ui_subscribers[team_id]:
                del self.ui_subscribers[team_id]
        logger.info(f"UI subscriber removed from team {team_id}")

    async def broadcast_presence(self, team_id: str, agent_id: str, status: str):
        envelope = HermesEnvelope(
            type="PRESENCE_UPDATE",
            team_id=team_id,
            agent_id=agent_id,
            payload={"status": status}
        )
        await self.broadcast_to_ui(team_id, envelope)

    async def broadcast_to_ui(self, team_id: str, envelope: HermesEnvelope):
        if team_id in self.ui_subscribers:
            disconnected = set()
            for ws in self.ui_subscribers[team_id]:
                try:
                    await self.send_to_websocket(ws, envelope)
                except Exception as e:
                    logger.error(f"Failed to send to UI subscriber: {e}")
                    disconnected.add(ws)
            
            for ws in disconnected:
                await self.unsubscribe_ui(team_id, ws)

    async def send_to_websocket(self, websocket: WebSocket, envelope: HermesEnvelope):
        await websocket.send_text(envelope.json())

    async def send_to_agent(self, agent_id: str, envelope: HermesEnvelope):
        """특정 에이전트에게 메시지 전송 (A2A 라우팅)."""
        if agent_id in self.agent_sessions:
            session = self.agent_sessions[agent_id]
            try:
                await self.send_to_websocket(session.websocket, envelope)
                return True
            except Exception as e:
                logger.error(f"Failed to send to agent {agent_id}: {e}")
                return False
        return False

# Global registry instance
hermes_registry = HermesRegistry()
