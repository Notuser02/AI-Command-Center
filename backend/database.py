import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, List
from models import TaskStatus, ApprovalStatus


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
                logs TEXT,
                messages TEXT
            )
        """)
        # Ensure 'messages' column exists for existing tables
        cursor = conn.execute("PRAGMA table_info(tasks)")
        cols = [r["name"] for r in cursor.fetchall()]
        if "messages" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN messages TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP
            )
        """)
        conn.commit()


class Task:
    def __init__(self, id: int, task: str, provider: str, status: str,
                 created_at: datetime, updated_at: datetime,
                 result: Optional[str] = None, logs: Optional[str] = None,
                 messages: Optional[str] = None):
        self.id = id
        self.task = task
        self.provider = provider
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.result = result
        self.logs = json.loads(logs) if logs else []
        self.messages = json.loads(messages) if messages else []


class TaskRepository:
    def __init__(self):
        pass

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        messages = row["messages"] if "messages" in row.keys() else None
        return Task(
            id=row["id"],
            task=row["task"],
            provider=row["provider"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=row["result"],
            logs=row["logs"],
            messages=messages
        )

    def create(self, task: str, provider: str = "local") -> Task:
        now = datetime.now(timezone.utc).isoformat()
        initial_messages = []
        if task and task.strip():
            initial_messages.append({
                "role": "user",
                "content": task,
                "timestamp": now
            })
        messages_json = json.dumps(initial_messages)
        with get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO tasks (task, provider, status, created_at, updated_at, messages)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task, provider, TaskStatus.PENDING.value, now, now, messages_json)
            )
            conn.commit()
            task_id = cursor.lastrowid
            return self.get(task_id)

    def append_message(self, task_id: int, role: str, content: str) -> List[dict]:
        task = self.get(task_id)
        if not task:
            return []
        messages = task.messages or []
        now = datetime.now(timezone.utc).isoformat()
        messages.append({
            "role": role,
            "content": content,
            "timestamp": now
        })
        with get_db() as conn:
            conn.execute(
                "UPDATE tasks SET messages = ?, updated_at = ? WHERE id = ?",
                (json.dumps(messages), now, task_id)
            )
            conn.commit()
        return messages

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


class Approval:
    def __init__(self, id: int, task_id: int, tool_name: str,
                 status: str, created_at: datetime,
                 arguments: Optional[str] = None, reason: Optional[str] = None,
                 resolved_at: Optional[datetime] = None):
        self.id = id
        self.task_id = task_id
        self.tool_name = tool_name
        self.status = status
        self.created_at = created_at
        self.arguments = json.loads(arguments) if arguments else None
        self.reason = reason
        self.resolved_at = resolved_at


class ApprovalRepository:
    def __init__(self):
        pass

    def _row_to_approval(self, row: sqlite3.Row) -> Approval:
        return Approval(
            id=row["id"],
            task_id=row["task_id"],
            tool_name=row["tool_name"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            arguments=row["arguments"],
            reason=row["reason"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
        )

    def create(self, task_id: int, tool_name: str, arguments: Optional[dict] = None, reason: Optional[str] = None) -> Approval:
        now = datetime.now(timezone.utc).isoformat()
        args_json = json.dumps(arguments) if arguments else None
        with get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO approvals (task_id, tool_name, arguments, reason, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, tool_name, args_json, reason, ApprovalStatus.PENDING.value, now)
            )
            conn.commit()
            approval_id = cursor.lastrowid
            return self.get(approval_id)

    def get(self, approval_id: int) -> Optional[Approval]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            return self._row_to_approval(row) if row else None

    def get_by_task(self, task_id: int) -> List[Approval]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE task_id = ? ORDER BY created_at DESC", (task_id,)
            ).fetchall()
            return [self._row_to_approval(row) for row in rows]

    def get_pending(self) -> List[Approval]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING.value,)
            ).fetchall()
            return [self._row_to_approval(row) for row in rows]

    def update_status(self, approval_id: int, status: ApprovalStatus) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                (status.value, now, approval_id)
            )
            conn.commit()
            return cursor.rowcount > 0