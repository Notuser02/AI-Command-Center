"""Verify the task deletion API (requires server on 127.0.0.1:8000)."""
import asyncio
import json
import time

import requests
import websockets

HTTP = "http://127.0.0.1:8000"
WS_URI = "ws://127.0.0.1:8000/ws"


async def catch_task_deleted(task_id):
    async with websockets.connect(WS_URI) as ws:
        await asyncio.wait_for(ws.recv(), 5)  # handshake
        requests.delete(f"{HTTP}/tasks/{task_id}", timeout=10)
        while True:
            ev = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if ev["event"] == "task_deleted":
                assert ev["data"]["task_id"] == task_id, ev
                return True


# 1. delete nonexistent -> 404
r = requests.delete(f"{HTTP}/tasks/99999", timeout=10)
assert r.status_code == 404, r.text
print("PASS: DELETE nonexistent task -> 404")

# 2. create + delete -> gone, and task_deleted broadcast on WS
r = requests.post(f"{HTTP}/tasks", json={"task": "delete me", "provider": "local"}, timeout=10)
tid = r.json()["id"]
assert asyncio.run(catch_task_deleted(tid))
print("PASS: task_deleted event broadcast over WebSocket")
r = requests.get(f"{HTTP}/tasks/{tid}", timeout=10)
assert r.status_code == 404, r.text
print("PASS: deleted task is gone from GET /tasks/{id}")

# 3. deleting a RUNNING task -> 400
r = requests.post(f"{HTTP}/tasks", json={
    "task": "Count slowly from 1 to 50 with detailed explanations. Do not use tools.",
    "provider": "local", "model": "qwen3.5:9b"
}, timeout=10)
tid2 = r.json()["id"]
requests.post(f"{HTTP}/tasks/{tid2}/start", timeout=10)
r = requests.delete(f"{HTTP}/tasks/{tid2}", timeout=10)
assert r.status_code == 400, r.text
assert "running" in r.json()["detail"], r.text
print("PASS: DELETE on running task -> 400 ('stop it first')")

# 4. stop it, then delete succeeds (cancellation lands between agent rounds,
#    so we may need to wait out the current LLM generation)
requests.post(f"{HTTP}/tasks/{tid2}/stop", timeout=10)
for _ in range(120):
    d = requests.get(f"{HTTP}/tasks/{tid2}", timeout=10).json()
    if d["status"] != "running":
        break
    time.sleep(1)
print(f"     task reached status '{d['status']}' after stop")
r = requests.delete(f"{HTTP}/tasks/{tid2}", timeout=10)
assert r.status_code == 200 and r.json()["deleted"], r.text
print("PASS: DELETE after stop -> 200")

print("\nALL DELETE TESTS PASSED")
