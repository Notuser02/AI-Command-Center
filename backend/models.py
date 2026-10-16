from enum import Enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    task: str
    provider: str = "local"


class TaskResponse(BaseModel):
    id: int
    task: str
    provider: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: Optional[str] = None
    logs: Optional[List] = None

    class Config:
        from_attributes = True


# ── Approval models ──────────────────────────────────────────────

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ApprovalResponse(BaseModel):
    id: int
    task_id: int
    tool_name: str
    arguments: Optional[dict] = None
    reason: Optional[str] = None
    status: ApprovalStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None