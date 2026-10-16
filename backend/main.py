import os
from fastapi import FastAPI, HTTPException
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider
from agent.agent import Agent
from agent.tools import ToolRegistry
from database import init_db, TaskRepository
from models import TaskCreate, TaskResponse, TaskStatus
from services.task_service import TaskService

app = FastAPI()

ollama = OllamaProvider()
nebius = NebiusProvider()

# ── Tool security: the agent can ONLY access files inside this directory ──
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
tool_registry = ToolRegistry(allowed_dirs=[PROJECT_DIR])

# Task service for background execution with concurrency control
task_service = TaskService(tool_registry)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/status")
def status():
    return {"status": "AI Command Center is running"}


@app.get("/chat")
def chat(message: str, provider: str = "local"):

    if provider == "local":
        response = ollama.generate(message)

    elif provider == "online":
        response = nebius.generate(message)

    else:
        response = "Unknown provider. Use 'local' or 'online'."

    return {
        "provider": provider,
        "response": response
    }


@app.post("/agent/run")
def run_agent(task: str, provider: str = "local"):

    if provider == "local":
        selected_provider = ollama

    elif provider == "online":
        selected_provider = nebius

    else:
        return {"error": "Unknown provider. Use 'local' or 'online'."}

    agent = Agent(selected_provider, tool_registry=tool_registry)

    result = agent.run(task)

    return {
        "provider": provider,
        "status": agent.status,
        "result": result,
        "logs": agent.logs
    }


# ── Task Management Endpoints ──

@app.post("/tasks", response_model=TaskResponse)
def create_task(task_in: TaskCreate):
    repo = TaskRepository()
    task = repo.create(task_in.task, task_in.provider)
    return TaskResponse(
        id=task.id,
        task=task.task,
        provider=task.provider,
        status=TaskStatus(task.status),
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        logs=task.logs
    )


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(limit: int = 50):
    repo = TaskRepository()
    tasks = repo.get_all(limit)
    return [
        TaskResponse(
            id=t.id,
            task=t.task,
            provider=t.provider,
            status=TaskStatus(t.status),
            created_at=t.created_at,
            updated_at=t.updated_at,
            result=t.result,
            logs=t.logs
        )
        for t in tasks
    ]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    repo = TaskRepository()
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id,
        task=task.task,
        provider=task.provider,
        status=TaskStatus(task.status),
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        logs=task.logs
    )


@app.post("/tasks/{task_id}/start", response_model=TaskResponse)
async def start_task(task_id: int):
    success = await task_service.start_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or not in pending status")
    repo = TaskRepository()
    task = repo.get(task_id)
    return TaskResponse(
        id=task.id,
        task=task.task,
        provider=task.provider,
        status=TaskStatus(task.status),
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        logs=task.logs
    )


@app.post("/tasks/{task_id}/stop", response_model=TaskResponse)
def stop_task(task_id: int):
    if not task_service.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="Task not running")
    repo = TaskRepository()
    task = repo.get(task_id)
    return TaskResponse(
        id=task.id,
        task=task.task,
        provider=task.provider,
        status=TaskStatus(task.status),
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        logs=task.logs
    )