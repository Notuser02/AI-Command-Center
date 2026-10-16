"""
Task management routes.

These endpoints handle the full task lifecycle:
  POST /tasks           → create a new task (status: pending)
  GET  /tasks           → list all tasks
  GET  /tasks/{id}      → get one task's details + logs
  POST /tasks/{id}/start → start running a task in the background
  POST /tasks/{id}/stop  → cancel a running task

Tasks run asynchronously — starting a task returns immediately,
and you poll GET /tasks/{id} to check progress. (WebSockets later.)
"""

from fastapi import APIRouter, HTTPException
from database import TaskRepository
from models import TaskCreate, TaskResponse, TaskStatus
from services.task_service import TaskService

router = APIRouter()

# Will be set by main.py when mounting this router
task_service: TaskService = None


def init(service: TaskService):
    """Called by main.py to inject the task service."""
    global task_service
    task_service = service


def _task_to_response(task) -> TaskResponse:
    """
    Convert a database Task to a TaskResponse.
    Extracted into a helper to avoid repeating this 5 times.
    """
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


@router.post("/tasks", response_model=TaskResponse)
def create_task(task_in: TaskCreate):
    repo = TaskRepository()
    task = repo.create(task_in.task, task_in.provider)
    return _task_to_response(task)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(limit: int = 50):
    repo = TaskRepository()
    tasks = repo.get_all(limit)
    return [_task_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    repo = TaskRepository()
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.post("/tasks/{task_id}/start", response_model=TaskResponse)
async def start_task(task_id: int):
    success = await task_service.start_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or not in pending status")
    repo = TaskRepository()
    task = repo.get(task_id)
    return _task_to_response(task)


@router.post("/tasks/{task_id}/stop", response_model=TaskResponse)
def stop_task(task_id: int):
    if not task_service.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="Task not running")
    repo = TaskRepository()
    task = repo.get(task_id)
    return _task_to_response(task)
