from enum import Enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)   # blank → UI shows TASK-<id>
    task: str = Field(default="", max_length=2000)             # description / agent context
    provider: str = "local"
    model: Optional[str] = "qwen3.5:9b"


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class TaskResponse(BaseModel):
    id: int
    name: Optional[str] = None
    task: str
    provider: str
    model: Optional[str] = "qwen3.5:9b"
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: Optional[str] = None
    logs: Optional[List] = None
    messages: Optional[List[dict]] = None

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