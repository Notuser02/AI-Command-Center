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


MAX_CONCURRENT_TASKS = 2


@dataclass
class RunningTask:
    task_id: int
    agent: Agent
    future: asyncio.Future


class TaskService:
    def __init__(self, tool_registry: ToolRegistry, max_concurrent: int = MAX_CONCURRENT_TASKS):
        self.tool_registry = tool_registry
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.running_tasks: Dict[int, RunningTask] = {}
        self.repo = TaskRepository()
        self._lock = threading.Lock()

    def _get_provider(self, provider_name: str):
        if provider_name == "local":
            return OllamaProvider()
        elif provider_name == "online":
            return NebiusProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def _run_task_background(self, task_id: int, agent: Agent, task: str):
        def progress_callback(logs):
            self.repo.update_logs(task_id, logs)

        async def run():
            try:
                result = await agent.run_async(task, progress_callback)
                self.repo.update_result(task_id, result)
                self.repo.update_status(task_id, TaskStatus.COMPLETED)
            except CancellationError:
                self.repo.update_status(task_id, TaskStatus.CANCELLED)
            except Exception as e:
                self.repo.update_result(task_id, f"Error: {e}")
                self.repo.update_status(task_id, TaskStatus.FAILED)
            finally:
                with self._lock:
                    self.running_tasks.pop(task_id, None)
                self.semaphore.release()

        asyncio.create_task(run())

    async def start_task(self, task_id: int) -> bool:
        task = self.repo.get(task_id)
        if not task or task.status != TaskStatus.PENDING.value:
            return False

        await self.semaphore.acquire()

        self.repo.update_status(task_id, TaskStatus.RUNNING)

        provider = self._get_provider(task.provider)
        agent = Agent(provider, tool_registry=self.tool_registry)

        with self._lock:
            self.running_tasks[task_id] = RunningTask(
                task_id=task_id,
                agent=agent,
                future=None
            )

        self._run_task_background(task_id, agent, task.task)
        return True

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