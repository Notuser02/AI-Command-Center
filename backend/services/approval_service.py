"""
Approval Service for Human-in-the-Loop agent authorization.

KEY CONCEPT:
When an agent attempts a sensitive action (e.g., executing a system command),
it pauses execution and requests human approval.

This service connects:
1. The background agent thread (waiting for approval via threading.Event)
2. The REST API / Mobile endpoints (where the user reviews and approves/denies)
3. The database (where approval history is persisted)
"""

import threading
import time
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass

from database import ApprovalRepository, Approval
from models import ApprovalStatus
from agent.agent import CancellationError


@dataclass
class ActiveApproval:
    approval_id: int
    event: threading.Event
    decision: Optional[bool] = None  # True: approved, False: denied


class ApprovalService:
    def __init__(self, repo: Optional[ApprovalRepository] = None, connection_manager=None):
        self.repo = repo or ApprovalRepository()
        self.connection_manager = connection_manager
        self._active: Dict[int, ActiveApproval] = {}
        self._lock = threading.Lock()

    def set_connection_manager(self, manager):
        self.connection_manager = manager

    def request_approval(
        self,
        task_id: int,
        tool_name: str,
        arguments: Optional[dict] = None,
        reason: Optional[str] = None
    ) -> Approval:
        """Create an approval record and register an active in-memory event."""
        approval = self.repo.create(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason
        )

        with self._lock:
            self._active[approval.id] = ActiveApproval(
                approval_id=approval.id,
                event=threading.Event(),
                decision=None
            )

        if self.connection_manager:
            self.connection_manager.broadcast("approval_required", {
                "approval_id": approval.id,
                "task_id": task_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "reason": reason,
                "status": approval.status,
                "created_at": str(approval.created_at)
            })

        return approval

    def wait_for_decision(
        self,
        approval_id: int,
        timeout: float = 300.0,
        check_cancelled: Optional[Callable[[], bool]] = None
    ) -> bool:
        """
        Blocks the calling thread until:
        1. User approves (returns True)
        2. User denies (returns False)
        3. Task is cancelled (raises CancellationError)
        4. Timeout expires (returns False, marks expired)
        """
        with self._lock:
            active = self._active.get(approval_id)

        if not active:
            # Check DB if already resolved
            app = self.repo.get(approval_id)
            return app is not None and app.status == ApprovalStatus.APPROVED.value

        start_time = time.time()
        poll_interval = 0.5

        try:
            while not active.event.is_set():
                if check_cancelled and check_cancelled():
                    self.repo.update_status(approval_id, ApprovalStatus.DENIED)
                    raise CancellationError("Task was cancelled while waiting for approval.")

                if time.time() - start_time >= timeout:
                    self.repo.update_status(approval_id, ApprovalStatus.EXPIRED)
                    if self.connection_manager:
                        self.connection_manager.broadcast("approval_resolved", {
                            "approval_id": approval_id,
                            "status": ApprovalStatus.EXPIRED.value
                        })
                    return False

                active.event.wait(timeout=poll_interval)

            return active.decision is True

        finally:
            with self._lock:
                self._active.pop(approval_id, None)

    def resolve(self, approval_id: int, approved: bool) -> bool:
        """Resolve a pending approval from an API endpoint."""
        app = self.repo.get(approval_id)
        if not app or app.status != ApprovalStatus.PENDING.value:
            return False

        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        self.repo.update_status(approval_id, new_status)

        if self.connection_manager:
            self.connection_manager.broadcast("approval_resolved", {
                "approval_id": approval_id,
                "status": new_status.value
            })

        with self._lock:
            active = self._active.get(approval_id)
            if active:
                active.decision = approved
                active.event.set()

        return True

    def get_pending(self) -> List[Approval]:
        return self.repo.get_pending()

    def get_by_task(self, task_id: int) -> List[Approval]:
        return self.repo.get_by_task(task_id)

    def get(self, approval_id: int) -> Optional[Approval]:
        return self.repo.get(approval_id)
