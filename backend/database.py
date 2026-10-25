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
                name TEXT,
                task TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'local',
                model TEXT DEFAULT 'qwen3.5:9b',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                result TEXT,
                logs TEXT,
                messages TEXT
            )
        """)
        # Ensure 'messages', 'model' and 'name' columns exist for existing tables
        cursor = conn.execute("PRAGMA table_info(tasks)")
        cols = [r["name"] for r in cursor.fetchall()]
        if "messages" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN messages TEXT")
        if "model" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN model TEXT DEFAULT 'qwen3.5:9b'")
        if "name" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN name TEXT")

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


class Task:
    def __init__(self, id: int, task: str, provider: str, status: str,
                 created_at: datetime, updated_at: datetime,
                 result: Optional[str] = None, logs: Optional[str] = None,
                 messages: Optional[str] = None, model: Optional[str] = "qwen3.5:9b",
                 name: Optional[str] = None):
        self.id = id
        self.name = name
        self.task = task
        self.provider = provider
        self.model = model or "qwen3.5:9b"
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
        model = row["model"] if "model" in row.keys() else "qwen3.5:9b"
        name = row["name"] if "name" in row.keys() else None
        return Task(
            id=row["id"],
            name=name,
            task=row["task"],
            provider=row["provider"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=row["result"],
            logs=row["logs"],
            messages=messages,
            model=model
        )

    def create(self, task: str, provider: str = "local", model: str = "qwen3.5:9b",
               name: Optional[str] = None) -> Task:
        """
        Create a task workspace. No first message is seeded — the
        conversation starts when the user sends the first instruction.
        `task` holds the description (context for the agent).
        """
        now = datetime.now(timezone.utc).isoformat()
        messages_json = json.dumps([])
        with get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO tasks (name, task, provider, model, status, created_at, updated_at, messages)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, task or "", provider, model or "qwen3.5:9b",
                 TaskStatus.PENDING.value, now, now, messages_json)
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

    def delete(self, task_id: int) -> bool:
        """Permanently remove a task and its approval history."""
        with get_db() as conn:
            # approvals reference tasks by id — remove them first
            # so no orphaned approval rows are left behind
            conn.execute("DELETE FROM approvals WHERE task_id = ?", (task_id,))
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def reset_stale_running(self) -> int:
        """
        Mark tasks stuck in 'running' as failed.

        Called once at server startup: if the server crashed or was stopped
        while a task was executing, that task's status was never updated and
        it would otherwise show 'running' forever.
        Returns how many rows were fixed.
        """
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                """UPDATE tasks
                   SET status = ?,
                       result = COALESCE(result, 'Interrupted: the server restarted while this task was running.'),
                       updated_at = ?
                   WHERE status = ?""",
                (TaskStatus.FAILED.value, now, TaskStatus.RUNNING.value)
            )
            conn.commit()
            return cursor.rowcount or 0


class SettingsRepository:
    """Simple key/value store for runtime config (e.g. online provider
    base URL + API key). Lives in tasks.db, which is gitignored —
    secrets stay on this machine."""

    def get(self, key: str) -> Optional[str]:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )
            conn.commit()

    def delete(self, key: str) -> None:
        with get_db() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()


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