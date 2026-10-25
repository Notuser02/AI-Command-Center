"""
SessionLogger — a plain-text journal of everything that happens in a task.

One file per task in backend/sessions/ (task_<id>_<name>.txt), appended on
events (messages, tool calls, statuses, approvals), deleted together with
the task. Deliberately writes EVENTS ONLY — never per streamed token — so
the cost is a handful of tiny appends per agent turn.

Format:
    [2026-10-25 14:03:11] EVENT TEXT
"""

import os
import re
import glob
from datetime import datetime

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sessions")
SESSIONS_DIR = os.path.abspath(SESSIONS_DIR)

# How much of any single event payload (tool results, answers) lands in the log
MAX_ENTRY_CHARS = 2000


def _slugify(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())
    return name.strip("_")[:40] or "unnamed"


def _files_for(task_id: int):
    """Session file paths for a task id (name may have changed over time —
    we keep the first file found for the id as the canonical one)."""
    return glob.glob(os.path.join(SESSIONS_DIR, f"task_{task_id}_*.txt"))


def log_event(task_id: int, name: str, text: str) -> None:
    """Append one timestamped line to the task's session file."""
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        existing = _files_for(task_id)
        if existing:
            path = existing[0]
        else:
            path = os.path.join(SESSIONS_DIR, f"task_{task_id}_{_slugify(name)}.txt")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = (text or "").strip().replace("\r", "")
        if len(body) > MAX_ENTRY_CHARS:
            body = body[:MAX_ENTRY_CHARS] + " …[truncated]"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {body}\n")
    except OSError:
        # Logging must never break the actual work
        pass


def delete_session(task_id: int, name: str = "") -> None:
    """Remove the task's session file (called when the task is deleted)."""
    for path in _files_for(task_id):
        try:
            os.remove(path)
        except OSError:
            pass
