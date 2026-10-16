import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, List
from models import TaskStatus


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'local',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                result TEXT,
                logs TEXT
            )
        """)
        conn.commit()


class Task:
    def __init__(self, id: int, task: str, provider: str, status: str,
                 created_at: datetime, updated_at: datetime,
                 result: Optional[str] = None, logs: Optional[str] = None):
        self.id = id
        self.task = task
        self.provider = provider
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.result = result
        self.logs = json.loads(logs) if logs else None


class TaskRepository:
    def __init__(self):
        pass

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            task=row["task"],
            provider=row["provider"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=row["result"],
            logs=row["logs"]
        )

    def create(self, task: str, provider: str = "local") -> Task:
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO tasks (task, provider, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task, provider, TaskStatus.PENDING.value, now, now)
            )
            conn.commit()
            task_id = cursor.lastrowid
            return self.get(task_id)

    def get(self, task_id: int) -> Optional[Task]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return self._row_to_task(row) if row else None

    def get_all(self, limit: int = 50) -> List[Task]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def update_status(self, task_id: int, status: TaskStatus) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_result(self, task_id: int, result: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET result = ?, updated_at = ? WHERE id = ?",
                (result, now, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_logs(self, task_id: int, logs: list) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        logs_json = json.dumps(logs)
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET logs = ?, updated_at = ? WHERE id = ?",
                (logs_json, now, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_updated_at(self, task_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ?",
                (now, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0