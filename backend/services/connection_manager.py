"""
WebSocket Connection Manager.

KEY ARCHITECTURAL CONCEPT: Thread-to-Event-Loop Communication.
The FastAPI server runs an asynchronous event loop (asyncio).
However, long-running agent reasoning and tool executions run in background
worker threads.

When a worker thread produces a log or requests approval, it cannot directly
`await websocket.send_text()`. Instead, `broadcast()` uses
`asyncio.run_coroutine_threadsafe()` to schedule the message send onto
FastAPI's main event loop.

This allows real-time push events from anywhere in the system to connected phones/clients.
"""

import json
import asyncio
from typing import List, Optional, Any
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Store reference to FastAPI's running event loop."""
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        """Accept incoming connection and add to active pool."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection from active pool."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_async(self, event: str, data: Any):
        """Send a structured JSON event to all active clients."""
        payload = json.dumps({"event": event, "data": data}, default=str)
        dead_connections = []

        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    def broadcast(self, event: str, data: Any):
        """
        Thread-safe broadcast.
        Safe to call from worker threads, callbacks, or async functions.
        """
        if not self.active_connections:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast_async(event, data),
                self._loop
            )
        else:
            try:
                # If currently inside an active event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast_async(event, data))
            except Exception:
                pass
