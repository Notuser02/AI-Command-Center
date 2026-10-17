"""
AI Command Center — main entry point.

This file creates the FastAPI app and mounts the route modules.
All endpoint logic lives in the api/ folder.

WHY THIS STRUCTURE:
  Before: main.py had ALL endpoints (165 lines, growing fast).
  Now:    main.py just wires things together (~30 lines).
          Each api/ file owns its own routes.
          Adding new features = adding new files, not growing one giant file.

Run with:  uvicorn main:app --reload
"""

import os
import asyncio
from fastapi import FastAPI
from database import init_db
from agent.tools import ToolRegistry
from services.task_service import TaskService
from services.approval_service import ApprovalService
from services.connection_manager import ConnectionManager

# ── Route modules ──
from api import chat, agents, tasks, approvals, websocket

app = FastAPI(title="AI Command Center")

# ── Tool security: the agent can ONLY access files inside this directory ──
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
tool_registry = ToolRegistry(allowed_dirs=[PROJECT_DIR])

# ── Initialize services ──
connection_manager = ConnectionManager()
approval_service = ApprovalService(connection_manager=connection_manager)
task_service = TaskService(
    tool_registry,
    approval_service=approval_service,
    connection_manager=connection_manager
)

# ── Inject dependencies into route modules ──
agents.init(tool_registry)
tasks.init(task_service)
approvals.init(approval_service)
websocket.init(connection_manager)

# ── Mount routers ──
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(websocket.router)


@app.on_event("startup")
def startup():
    init_db()
    # Provide the running event loop to connection_manager for threadsafe broadcasts
    connection_manager.set_loop(asyncio.get_running_loop())