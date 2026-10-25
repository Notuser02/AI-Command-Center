"""
Task management routes.

These endpoints handle the full task lifecycle:
  POST   /tasks           → create a new task (status: pending)
  GET    /tasks           → list all tasks
  GET    /tasks/{id}      → get one task's details + logs
  POST   /tasks/{id}/start → start running a task in the background
  POST   /tasks/{id}/stop  → cancel a running task
  POST   /tasks/{id}/complete → archive a finished conversation
  DELETE /tasks/{id}      → permanently delete a task + its history

Tasks run asynchronously — starting a task returns immediately,
and you poll GET /tasks/{id} to check progress. (WebSockets later.)
"""

from fastapi import APIRouter, HTTPException
from database import TaskRepository
from models import TaskCreate, MessageCreate, TaskResponse, TaskStatus
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
    Extracted into a helper to avoid repeating this.
    """
    return TaskResponse(
        id=task.id,
        name=getattr(task, "name", None),
        task=task.task,
        provider=task.provider,
        model=getattr(task, "model", "qwen3.5:9b"),
        status=TaskStatus(task.status),
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        logs=task.logs,
        messages=task.messages
    )


@router.post("/tasks", response_model=TaskResponse)
def create_task(task_in: TaskCreate):
    repo = TaskRepository()
    task = repo.create(task_in.task, task_in.provider, model=task_in.model,
                       name=(task_in.name or None))
    # Session journal: one plain-text file per task (see services/session_logger.py)
    from services.session_logger import log_event
    log_event(task.id, task.name,
              f"TASK CREATED: {task.name or ('TASK-' + str(task.id))} | "
              f"description: {task.task or '(none)'} | "
              f"provider: {task.provider} | model: {task.model}")
    resp = _task_to_response(task)
    if task_service and task_service.connection_manager:
        task_service.connection_manager.broadcast("task_created", resp.model_dump())
    return resp


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


@router.post("/tasks/{task_id}/messages", response_model=TaskResponse)
async def send_message_to_task(task_id: int, message_in: MessageCreate):
    """
    Send a message / instruction into an existing task conversation.
    The agent retains all prior context and history from this task!
    """
    success = await task_service.send_message(task_id, message_in.message)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task not found or is currently executing another turn"
        )
    repo = TaskRepository()
    task = repo.get(task_id)
    return _task_to_response(task)


@router.post("/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: int):
    """Mark a task conversation as completed."""
    success = task_service.complete_task(task_id)
    if not success:
        repo = TaskRepository()
        if repo.get(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(
            status_code=400,
            detail="Task is currently running — stop it before finishing it"
        )
    repo = TaskRepository()
    task = repo.get(task_id)
    return _task_to_response(task)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    """
    Permanently delete a task and its history.
    Refuses with 400 while the task is running (stop it first).
    """
    success = task_service.delete_task(task_id)
    if not success:
        repo = TaskRepository()
        if repo.get(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(
            status_code=400,
            detail="Task is currently running — stop it before deleting"
        )
    return {"deleted": True, "id": task_id}
