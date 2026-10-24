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
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, TaskRepository
from agent.tools import ToolRegistry
from services.task_service import TaskService
from services.approval_service import ApprovalService
from services.connection_manager import ConnectionManager

# ── Route modules ──
from api import chat, agents, tasks, approvals, websocket


# ── Lifespan: runs once on startup, cleans up on shutdown ──
# (The modern replacement for @app.on_event("startup"), which FastAPI
#  has deprecated. Everything before `yield` runs at startup.)
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # Recover tasks left in 'running' by a previous server crash/restart
    stale = TaskRepository().reset_stale_running()
    if stale:
        print(f"[startup] Recovered {stale} task(s) stuck in 'running' state (marked failed).")

    # Provide the running event loop to connection_manager for threadsafe broadcasts
    connection_manager.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="AI Command Center", lifespan=lifespan)

# CORS: the mobile app (React Native) doesn't need it, but Expo's web mode
# and browser-based debugging do — a LAN-served dev tool, so allow all origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Tool security: the agent can ONLY access files inside these directories ──
# The backend folder itself is always allowed; extra folders (e.g. the
# Desktop) come from allowed_dirs.txt — one absolute path per line.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_extra_allowed_dirs():
    """Read user-configured extra sandbox folders from allowed_dirs.txt."""
    config_path = os.path.join(PROJECT_DIR, "allowed_dirs.txt")
    dirs = []
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    dirs.append(os.path.abspath(line))
    return dirs


tool_registry = ToolRegistry(allowed_dirs=[PROJECT_DIR] + _load_extra_allowed_dirs())

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

# ── Web Browser CLI Dashboard ──
STATIC_DIR = os.path.join(PROJECT_DIR, "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=FileResponse)
def serve_dashboard():
    return FileResponse(INDEX_HTML)

@app.get("/dashboard", response_class=FileResponse)
def serve_dashboard_alias():
    return FileResponse(INDEX_HTML)