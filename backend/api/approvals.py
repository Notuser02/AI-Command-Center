"""
Approval routes for Human-in-the-Loop decision making.

Endpoints:
  GET  /approvals/pending            → List all pending approval requests
  GET  /approvals/{approval_id}       → Get details of a specific approval
  POST /approvals/{approval_id}/approve → Approve a sensitive agent action
  POST /approvals/{approval_id}/deny    → Deny a sensitive agent action
"""

from typing import List
from fastapi import APIRouter, HTTPException

from models import ApprovalResponse, ApprovalStatus
from services.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["approvals"])

approval_service: ApprovalService = None


def init(service: ApprovalService):
    """Called by main.py to inject the approval service instance."""
    global approval_service
    approval_service = service


def _approval_to_response(app) -> ApprovalResponse:
    return ApprovalResponse(
        id=app.id,
        task_id=app.task_id,
        tool_name=app.tool_name,
        arguments=app.arguments,
        reason=app.reason,
        status=ApprovalStatus(app.status),
        created_at=app.created_at,
        resolved_at=app.resolved_at
    )


@router.get("/pending", response_model=List[ApprovalResponse])
def get_pending_approvals():
    """List all approvals currently awaiting human decision."""
    approvals = approval_service.get_pending()
    return [_approval_to_response(a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(approval_id: int):
    """Get the details and status of a specific approval."""
    app = approval_service.get(approval_id)
    if not app:
        raise HTTPException(status_code=404, detail="Approval not found")
    return _approval_to_response(app)


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_action(approval_id: int):
    """Approve a sensitive agent action."""
    success = approval_service.resolve(approval_id, approved=True)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Approval not found or not in pending status"
        )
    app = approval_service.get(approval_id)
    return _approval_to_response(app)


@router.post("/{approval_id}/deny", response_model=ApprovalResponse)
def deny_action(approval_id: int):
    """Deny a sensitive agent action."""
    success = approval_service.resolve(approval_id, approved=False)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Approval not found or not in pending status"
        )
    app = approval_service.get(approval_id)
    return _approval_to_response(app)
