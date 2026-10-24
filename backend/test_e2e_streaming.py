"""
End-to-end streaming integration test.

Requires the server running on 127.0.0.1:8000.
Verifies that task_token events stream live during a real task,
followed by the final task_message and idle status.
"""
import asyncio
import json
import sys
import os

import requests
import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WS_URI = "ws://127.0.0.1:8000/ws"
HTTP = "http://127.0.0.1:8000"
BACKEND = os.path.dirname(os.path.abspath(__file__))


async def main():
    async with websockets.connect(WS_URI) as ws:
        greeting = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert greeting["event"] == "connected"
        print("connected to", WS_URI)

        resp = requests.post(f"{HTTP}/tasks", json={
            "task": f"Read the file main.py in {BACKEND} and reply with a one-sentence summary. Then write the word DONE.",
            "provider": "local",
            "model": "qwen3.5:9b",
        }, timeout=10)
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["id"]
        print(f"created task #{task_id}")

        # consume the task_created event
        ev = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert ev["event"] == "task_created", ev

        requests.post(f"{HTTP}/tasks/{task_id}/start", timeout=10)
        print("task started — listening for stream…")

        token_count = 0
        streamed_text = ""
        tool_events = 0
        final_message = None
        status = None

        while True:
            raw = await asyncio.wait_for(ws.recv(), 300)
            ev = json.loads(raw)
            etype, data = ev["event"], ev.get("data", {})

            if etype == "task_token" and data.get("task_id") == task_id:
                token_count += 1
                streamed_text += data.get("delta", "")
                if token_count % 20 == 0:
                    print(f"  …{token_count} tokens streamed")
            elif etype == "task_log" and data.get("task_id") == task_id:
                log = data.get("log", {})
                if log.get("type") in ("tool_call", "tool_result"):
                    tool_events += 1
                    print(f"  tool event: {log.get('type')} {log.get('tool')}")
            elif etype == "task_message" and data.get("task_id") == task_id:
                if data.get("role") == "assistant":
                    final_message = data.get("content", "")
            elif etype == "task_status_changed" and data.get("task_id") == task_id:
                status = data.get("status")
                print(f"  status -> {status}")
                if status in ("idle", "failed", "cancelled"):
                    break

        assert token_count > 5, f"expected live tokens, got {token_count}"
        assert tool_events >= 1, "expected at least one tool call"
        assert final_message, "expected final assistant message"
        assert status == "idle", f"final status was {status}"
        assert final_message.strip().startswith(streamed_text.strip()[:20]) or streamed_text.strip()[:20] in final_message, \
            "streamed text should be a prefix/substring of final message"

        print(f"\nPASS: {token_count} tokens streamed live, {tool_events} tool call(s), "
              f"final answer {len(final_message)} chars, status=idle")
        print("FINAL:", final_message[:200].replace("\n", " "))


if __name__ == "__main__":
    asyncio.run(main())
