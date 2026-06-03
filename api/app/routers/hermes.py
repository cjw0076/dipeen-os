from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.services.hermes_registry import hermes_registry
from app.schemas.hermes import HermesEnvelope
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/hermes/agent")
async def hermes_agent_endpoint(
    websocket: WebSocket,
    agent_id: str = Query(...),
    team_id: str = Query(...)
):
    await websocket.accept()
    await hermes_registry.register_agent(agent_id, team_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                envelope = HermesEnvelope(**msg)
                
                # Handle incoming agent messages
                if envelope.type == "NODE_HELLO":
                    logger.info(f"Agent {agent_id} said HELLO")
                elif envelope.type == "LOG_STREAM":
                    # Broadcast logs to UI subscribers
                    await hermes_registry.broadcast_to_ui(team_id, envelope)
                elif envelope.type == "A2A_MSG":
                    # Route A2A message to target agent
                    target_id = envelope.payload.get("to_agent_id")
                    if target_id:
                        success = await hermes_registry.send_to_agent(target_id, envelope)
                        if not success:
                            # If target offline, send error back to sender
                            error_env = HermesEnvelope(
                                type="ERROR",
                                team_id=team_id,
                                agent_id="HQ",
                                reply_to=envelope.id,
                                payload={"reason": f"Agent {target_id} is offline or not found"}
                            )
                            await websocket.send_text(error_env.json())
                
            except Exception as e:
                logger.error(f"Error processing Hermes message from agent {agent_id}: {e}")
                
    except WebSocketDisconnect:
        await hermes_registry.unregister_agent(agent_id)
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
        await hermes_registry.unregister_agent(agent_id)

@router.websocket("/ws/hermes/ui")
async def hermes_ui_endpoint(
    websocket: WebSocket,
    team_id: str = Query(...)
):
    await websocket.accept()
    await hermes_registry.subscribe_ui(team_id, websocket)
    
    try:
        while True:
            # UI typically mostly subscribes, but can send commands
            data = await websocket.receive_text()
            # Handle UI commands if needed
    except WebSocketDisconnect:
        await hermes_registry.unsubscribe_ui(team_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error for UI subscriber on team {team_id}: {e}")
        await hermes_registry.unsubscribe_ui(team_id, websocket)
