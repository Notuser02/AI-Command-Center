"""
WebSocket Integration Test Script.

Tests:
1. Connect to ws://127.0.0.1:8000/ws
2. Verify initial handshake message: {"event": "connected"}
3. Send ping and verify pong
4. Listen for real-time broadcast events when a task is created and executed
"""

import asyncio
import json
import requests
import websockets


WS_URI = "ws://127.0.0.1:8000/ws"
HTTP_BASE = "http://127.0.0.1:8000"


async def run_websocket_test():
    print(f"Connecting to WebSocket at {WS_URI}...")
    async with websockets.connect(WS_URI) as ws:
        # 1. Receive handshake
        greeting = await asyncio.wait_for(ws.recv(), timeout=5.0)
        greeting_data = json.loads(greeting)
        print("Handshake received:", greeting_data)
        assert greeting_data.get("event") == "connected", "Expected connected event"

        # 2. Test ping / pong
        await ws.send(json.dumps({"type": "ping"}))
        pong = await asyncio.wait_for(ws.recv(), timeout=5.0)
        pong_data = json.loads(pong)
        print("Ping response received:", pong_data)
        assert pong_data.get("event") == "pong", "Expected pong event"

        # 3. Trigger a task creation via HTTP while listening on WebSocket
        print("\nTriggering HTTP POST /tasks to test live event broadcast...")
        resp = requests.post(
            f"{HTTP_BASE}/tasks",
            json={"task": "List files in directory", "provider": "local"}
        )
        task_id = resp.json()["id"]
        print(f"Created task #{task_id} via REST API.")

        # 4. We should immediately receive 'task_created' over WebSocket without polling!
        created_event = await asyncio.wait_for(ws.recv(), timeout=5.0)
        created_data = json.loads(created_event)
        print("\n[WebSocket Event Caught]:", created_data["event"])
        print("Payload:", created_data["data"])
        assert created_data.get("event") == "task_created"
        assert created_data["data"]["id"] == task_id

        # 5. Start the task via HTTP
        print(f"\nStarting task #{task_id} via REST API...")
        requests.post(f"{HTTP_BASE}/tasks/{task_id}/start")

        # 6. Listen for task status change and logs streaming over WebSocket!
        print("\nStreaming real-time events over WebSocket:")
        completed = False
        while not completed:
            msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
            event_obj = json.loads(msg)
            event_type = event_obj.get("event")
            event_data = event_obj.get("data")
            print(f" -> Event: [{event_type}]")

            if event_type == "task_status_changed":
                status = event_data.get("status")
                print(f"    Task #{event_data.get('task_id')} status is now: {status}")
                if status in ["completed", "failed", "cancelled"]:
                    completed = True

            elif event_type == "task_log":
                log_entry = event_data.get("log", {})
                print(f"    [Agent Step {log_entry.get('step')}]: type={log_entry.get('type')}, tool={log_entry.get('tool')}")

            elif event_type == "approval_required":
                print(f"    [Approval Alert]: Approval #{event_data.get('approval_id')} required for {event_data.get('tool_name')}")

        print("\nSUCCESS: All events streamed in real-time over WebSocket with ZERO polling!")


if __name__ == "__main__":
    asyncio.run(run_websocket_test())
