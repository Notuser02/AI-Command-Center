import asyncio
import threading
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass

from database import TaskRepository
from models import TaskStatus
from agent.agent import Agent, CancellationError
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider
from agent.tools import ToolRegistry
import os


from services.approval_service import ApprovalService


MAX_CONCURRENT_TASKS = 2


@dataclass
class RunningTask:
    task_id: int
    agent: Agent
    future: asyncio.Future


class TaskService:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        approval_service: Optional[ApprovalService] = None,
        connection_manager=None,
        max_concurrent: int = MAX_CONCURRENT_TASKS
    ):
        self.tool_registry = tool_registry
        self.approval_service = approval_service
        self.connection_manager = connection_manager
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.running_tasks: Dict[int, RunningTask] = {}
        self.repo = TaskRepository()
        self._lock = threading.Lock()

    def set_connection_manager(self, manager):
        self.connection_manager = manager

    def _get_provider(self, provider_name: str):
        if provider_name == "local":
            return OllamaProvider()
        elif provider_name == "online":
            return NebiusProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def _run_task_background(self, task_id: int, agent: Agent, task: str, history=None):
        def progress_callback(logs):
            self.repo.update_logs(task_id, logs)
            if self.connection_manager and logs:
                self.connection_manager.broadcast("task_log", {
                    "task_id": task_id,
                    "log": logs[-1]
                })

        async def run():
            try:
                result = await agent.run_async(task, progress_callback, history=history)
                self.repo.append_message(task_id, role="assistant", content=result)
                self.repo.update_result(task_id, result)
                # Keep task in IDLE status so user can continue sending messages to it!
                self.repo.update_status(task_id, TaskStatus.IDLE)
                if self.connection_manager:
                    self.connection_manager.broadcast("task_message", {
                        "task_id": task_id,
                        "role": "assistant",
                        "content": result
                    })
                    self.connection_manager.broadcast("task_status_changed", {
                        "task_id": task_id,
                        "status": TaskStatus.IDLE.value,
                        "result": result
                    })
            except CancellationError:
                self.repo.update_status(task_id, TaskStatus.CANCELLED)
                if self.connection_manager:
                    self.connection_manager.broadcast("task_status_changed", {
                        "task_id": task_id,
                        "status": TaskStatus.CANCELLED.value
                    })
            except Exception as e:
                self.repo.update_result(task_id, f"Error: {e}")
                self.repo.update_status(task_id, TaskStatus.FAILED)
                if self.connection_manager:
                    self.connection_manager.broadcast("task_status_changed", {
                        "task_id": task_id,
                        "status": TaskStatus.FAILED.value,
                        "error": str(e)
                    })
            finally:
                with self._lock:
                    self.running_tasks.pop(task_id, None)
                self.semaphore.release()

        asyncio.create_task(run())

    async def start_task(self, task_id: int) -> bool:
        task = self.repo.get(task_id)
        if not task or task.status not in [TaskStatus.PENDING.value, TaskStatus.IDLE.value]:
            return False

        if self.is_task_running(task_id):
            return False

        await self.semaphore.acquire()

        self.repo.update_status(task_id, TaskStatus.RUNNING)
        if self.connection_manager:
            self.connection_manager.broadcast("task_status_changed", {
                "task_id": task_id,
                "status": TaskStatus.RUNNING.value
            })

        provider = self._get_provider(task.provider)
        agent = Agent(
            provider,
            tool_registry=self.tool_registry,
            approval_service=self.approval_service,
            task_id=task_id
        )

        with self._lock:
            self.running_tasks[task_id] = RunningTask(
                task_id=task_id,
                agent=agent,
                future=None
            )

        self._run_task_background(task_id, agent, task.task, history=task.messages or [])
        return True

    async def send_message(self, task_id: int, message: str) -> bool:
        task = self.repo.get(task_id)
        if not task:
            return False

        if self.is_task_running(task_id):
            return False

        # Add user message to history
        updated_messages = self.repo.append_message(task_id, role="user", content=message)

        if self.connection_manager:
            self.connection_manager.broadcast("task_message", {
                "task_id": task_id,
                "role": "user",
                "content": message
            })

        await self.semaphore.acquire()
        self.repo.update_status(task_id, TaskStatus.RUNNING)
        if self.connection_manager:
            self.connection_manager.broadcast("task_status_changed", {
                "task_id": task_id,
                "status": TaskStatus.RUNNING.value
            })

        provider = self._get_provider(task.provider)
        agent = Agent(
            provider,
            tool_registry=self.tool_registry,
            approval_service=self.approval_service,
            task_id=task_id
        )

        with self._lock:
            self.running_tasks[task_id] = RunningTask(
                task_id=task_id,
                agent=agent,
                future=None
            )

        self._run_task_background(task_id, agent, message, history=updated_messages)
        return True

    def complete_task(self, task_id: int) -> bool:
        """Mark task explicitly as completed / archived."""
        success = self.repo.update_status(task_id, TaskStatus.COMPLETED)
        if success and self.connection_manager:
            self.connection_manager.broadcast("task_status_changed", {
                "task_id": task_id,
                "status": TaskStatus.COMPLETED.value
            })
        return success

    def cancel_task(self, task_id: int) -> bool:
        with self._lock:
            running = self.running_tasks.get(task_id)
            if not running:
                return False
            running.agent.cancel()
        return True

    def get_running_count(self) -> int:
        with self._lock:
            return len(self.running_tasks)

    def is_task_running(self, task_id: int) -> bool:
        with self._lock:
            return task_id in self.running_tasks