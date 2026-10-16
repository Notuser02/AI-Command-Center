"""
Test script for the Human-in-the-Loop Approval System.

Tests:
1. ToolRegistry requires_approval check (safe vs. sensitive tools).
2. ApprovalService thread synchronization:
   - Thread A requests approval and waits.
   - Thread B approves -> Thread A unblocks with True.
3. ApprovalService denial:
   - Thread A requests approval and waits.
   - Thread B denies -> Thread A unblocks with False.
4. Database persistence for approvals.
"""

import threading
import time
import os

from database import init_db, ApprovalRepository
from models import ApprovalStatus
from services.approval_service import ApprovalService
from agent.tools import ToolRegistry

def test_tool_sensitivity():
    print("--- Test 1: Tool Sensitivity ---")
    reg = ToolRegistry(allowed_dirs=[os.path.abspath(".")])
    assert not reg.requires_approval("list_files"), "list_files should NOT require approval"
    assert not reg.requires_approval("read_file"), "read_file should NOT require approval"
    assert reg.requires_approval("run_command"), "run_command MUST require approval"
    print("PASS: Tool sensitivity correctly configured.")

def test_approval_resolution(approve: bool):
    test_name = "Approve" if approve else "Deny"
    print(f"--- Test: Approval Service ({test_name}) ---")
    service = ApprovalService()

    app = service.request_approval(
        task_id=999,
        tool_name="run_command",
        arguments={"command": "git status"},
        reason="Test execution"
    )

    pending = service.get_pending()
    assert any(p.id == app.id for p in pending), "Approval should be in pending list"
    print(f"Created pending approval #{app.id}")

    result_holder = {}

    def worker():
        decision = service.wait_for_decision(app.id, timeout=5.0)
        result_holder["decision"] = decision

    t = threading.Thread(target=worker)
    t.start()

    time.sleep(0.5)
    # Simulate user approving/denying from phone or API
    resolved = service.resolve(app.id, approved=approve)
    assert resolved, "Resolve should return True"

    t.join(timeout=2.0)
    assert not t.is_alive(), "Worker thread should have unblocked"
    assert result_holder.get("decision") == approve, f"Decision should be {approve}"

    # Verify DB update
    updated = service.get(app.id)
    expected_status = ApprovalStatus.APPROVED.value if approve else ApprovalStatus.DENIED.value
    assert updated.status == expected_status, f"DB status should be {expected_status}"
    print(f"PASS: Approval resolution ({test_name}) verified successfully.")

if __name__ == "__main__":
    init_db()
    test_tool_sensitivity()
    test_approval_resolution(approve=True)
    test_approval_resolution(approve=False)
    print("\nALL APPROVAL TESTS PASSED!")
