"""
WebSocket router for real-time streaming of Command Center events.

Endpoint:
  ws://127.0.0.1:8000/ws
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.connection_manager import ConnectionManager

router = APIRouter(tags=["websocket"])

connection_manager: ConnectionManager = None


def init(manager: ConnectionManager):
    """Called by main.py to inject the shared connection manager."""
    global connection_manager
    connection_manager = manager


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)

    # Send handshake confirmation
    await websocket.send_text(json.dumps({
        "event": "connected",
        "data": {
            "message": "Connected to AI Command Center real-time stream"
        }
    }))

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
                msg_type = msg.get("type") or msg.get("event")

                # Heartbeat / Ping-Pong support
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
            except json.JSONDecodeError:
                # Raw text message fallback
                if raw_text.strip().lower() == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception:
        connection_manager.disconnect(websocket)
