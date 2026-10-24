"""
AI Command Center — Real-Time PC Terminal Dashboard (CLI GUI).

A live terminal interface visualizing:
- Active & recent tasks
- Agent execution states & tool calls
- Live streaming logs over WebSocket
- Human-in-the-Loop approval alerts
- System metrics & connection status

Usage:
    python cli_dashboard.py [--server http://127.0.0.1:8000]
"""

import sys
import os
import json
import time
import asyncio
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

# Ensure UTF-8 console encoding on Windows to prevent charmap errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
import websockets
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align


DEFAULT_HTTP_URL = "http://127.0.0.1:8000"
DEFAULT_WS_URL = "ws://127.0.0.1:8000/ws"


class DashboardState:
    def __init__(self):
        self.connected = False
        self.server_url = DEFAULT_HTTP_URL
        self.ws_url = DEFAULT_WS_URL
        self.tasks: List[Dict[str, Any]] = []
        self.feed_logs: List[Dict[str, Any]] = []
        self.pending_approvals: List[Dict[str, Any]] = []
        self.last_update = datetime.now()
        self.model_name = "qwen3.5:9b (Local Ollama)"
        self._lock = threading.Lock()

    def add_log(self, text: str, style: str = "white", category: str = "INFO"):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.feed_logs.append({
                "time": ts,
                "text": text,
                "style": style,
                "category": category
            })
            if len(self.feed_logs) > 100:
                self.feed_logs.pop(0)

    def set_connected(self, status: bool):
        with self._lock:
            self.connected = status

    def update_tasks(self, tasks: List[Dict[str, Any]]):
        with self._lock:
            self.tasks = tasks

    def update_task_status(self, task_id: int, status: str, result: Optional[str] = None):
        with self._lock:
            for t in self.tasks:
                if t.get("id") == task_id:
                    t["status"] = status
                    if result:
                        t["result"] = result
                    return
            # If not in local cache, will reload next cycle
            self.tasks.append({"id": task_id, "task": f"Task #{task_id}", "status": status, "provider": "local"})

    def add_pending_approval(self, approval_data: Dict[str, Any]):
        with self._lock:
            # Avoid duplicates
            self.pending_approvals = [
                a for a in self.pending_approvals if a.get("approval_id") != approval_data.get("approval_id")
            ]
            self.pending_approvals.append(approval_data)

    def remove_pending_approval(self, approval_id: int):
        with self._lock:
            self.pending_approvals = [
                a for a in self.pending_approvals
                if a.get("approval_id") != approval_id and a.get("id") != approval_id
            ]


state = DashboardState()


def fetch_initial_data():
    """Fetch recent tasks and pending approvals via REST API."""
    try:
        r = requests.get(f"{state.server_url}/tasks?limit=15", timeout=3.0)
        if r.status_code == 200:
            state.update_tasks(r.json())

        app_r = requests.get(f"{state.server_url}/approvals/pending", timeout=3.0)
        if app_r.status_code == 200:
            with state._lock:
                state.pending_approvals = app_r.json()

        state.set_connected(True)
    except Exception:
        state.set_connected(False)


async def websocket_listener():
    """Connect to FastAPI WebSocket and process incoming real-time events."""
    while True:
        try:
            state.add_log(f"Connecting to {state.ws_url}...", style="cyan", category="NET")
            async with websockets.connect(state.ws_url) as ws:
                state.set_connected(True)
                state.add_log("WebSocket connected. Real-time stream active.", style="green", category="NET")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    event_type = data.get("event")
                    payload = data.get("data", {})

                    if event_type == "connected":
                        state.add_log(payload.get("message", "Stream ready"), style="green", category="SYS")

                    elif event_type == "task_created":
                        t_id = payload.get("id")
                        t_desc = payload.get("task", "")
                        state.add_log(f"New Task #{t_id} created: {t_desc[:40]}", style="bright_blue", category="TASK")
                        fetch_initial_data()

                    elif event_type == "task_status_changed":
                        t_id = payload.get("task_id")
                        st = payload.get("status")
                        style = "yellow" if st == "running" else "green" if st == "completed" else "red"
                        state.add_log(f"Task #{t_id} changed to [{st.upper()}]", style=style, category="STATUS")
                        state.update_task_status(t_id, st, payload.get("result"))

                    elif event_type == "task_log":
                        t_id = payload.get("task_id")
                        log = payload.get("log", {})
                        log_type = log.get("type")
                        tool = log.get("tool")
                        if log_type == "tool_call":
                            state.add_log(f"Task #{t_id} calling tool: {tool}", style="magenta", category="TOOL")
                        elif log_type == "tool_result":
                            res_snip = str(log.get("result", ""))[:60].replace("\n", " ")
                            state.add_log(f"Task #{t_id} tool output: {res_snip}...", style="dim white", category="TOOL")
                        elif log_type == "final_answer":
                            state.add_log(f"Task #{t_id} formulated final answer.", style="bright_green", category="AGENT")
                        elif log_type == "approval_required":
                            state.add_log(f"Task #{t_id} paused for APPROVAL!", style="bold yellow", category="SECURITY")

                    elif event_type == "approval_required":
                        app_id = payload.get("approval_id")
                        tool = payload.get("tool_name")
                        state.add_pending_approval(payload)
                        state.add_log(f"ALERT: Approval #{app_id} requested for '{tool}'", style="bold red on yellow", category="APPROVAL")

                    elif event_type == "approval_resolved":
                        app_id = payload.get("approval_id")
                        res_status = payload.get("status")
                        state.remove_pending_approval(app_id)
                        color = "green" if res_status == "approved" else "red"
                        state.add_log(f"Approval #{app_id} resolved: {res_status.upper()}", style=color, category="APPROVAL")

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
            state.set_connected(False)
            state.add_log("WebSocket connection lost. Retrying in 3s...", style="red", category="NET")
            await asyncio.sleep(3.0)
        except Exception as e:
            state.set_connected(False)
            state.add_log(f"Stream error: {e}", style="red", category="ERR")
            await asyncio.sleep(3.0)


def start_background_listener():
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(websocket_listener())

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()


# ── UI Rendering Helpers ─────────────────────────────────────────

def build_header_panel() -> Panel:
    title = Text(" AI COMMAND CENTER ", style="bold black on bright_cyan")
    sub = Text(" // PC LIVE MONITOR // ", style="bold bright_cyan")

    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="right", ratio=1)

    status_badge = (
        Text("● ONLINE", style="bold green") if state.connected else Text("○ OFFLINE", style="bold red")
    )
    clock = Text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), style="dim white")
    model_info = Text(f"MODEL: {state.model_name}", style="bright_magenta")

    left_content = Text.assemble(title, " ", sub)
    center_content = model_info
    right_content = Text.assemble("STATUS: ", status_badge, "  |  ", clock)

    grid.add_row(left_content, center_content, right_content)
    return Panel(grid, style="cyan", border_style="bright_cyan")


def build_tasks_panel() -> Panel:
    table = Table(expand=True, box=None, padding=(0, 1))
    table.add_column("ID", justify="right", style="cyan", width=4)
    table.add_column("Task Description", justify="left", style="white", ratio=1)
    table.add_column("Provider", justify="center", style="dim", width=8)
    table.add_column("Status", justify="center", width=12)

    with state._lock:
        task_list = list(state.tasks)[:12]

    if not task_list:
        table.add_row("-", "No tasks in database yet", "-", "-")
    else:
        for t in task_list:
            t_id = str(t.get("id", "-"))
            desc = str(t.get("name") or t.get("task") or "")
            if len(desc) > 38:
                desc = desc[:35] + "..."
            prov = str(t.get("provider", "local"))
            status = str(t.get("status", "pending")).lower()

            if status == "running":
                status_widget = Text("● RUNNING", style="bold yellow")
            elif status == "completed":
                status_widget = Text("✔ DONE", style="bold green")
            elif status == "failed":
                status_widget = Text("✖ FAILED", style="bold red")
            elif status == "cancelled":
                status_widget = Text("⊘ CANCEL", style="bold dark_orange")
            else:
                status_widget = Text("○ PENDING", style="dim white")

            table.add_row(t_id, desc, prov, status_widget)

    # Task metrics
    running_count = sum(1 for t in state.tasks if t.get("status") == "running")
    completed_count = sum(1 for t in state.tasks if t.get("status") == "completed")
    title_text = f"ACTIVE TASKS ({len(state.tasks)} Total | [yellow]{running_count} Running[/] | [green]{completed_count} Completed[/])"

    return Panel(
        table,
        title=f"[bold]{title_text}[/]",
        border_style="bright_blue",
        padding=(0, 0)
    )


def build_feed_panel() -> Panel:
    text = Text()
    with state._lock:
        logs = list(state.feed_logs)[-18:]

    if not logs:
        text.append("Waiting for agent events...\n", style="dim italic")
    else:
        for l in logs:
            cat = f"[{l['category']}]".ljust(9)
            text.append(f"{l['time']} ", style="dim")
            text.append(f"{cat} ", style="bold bright_cyan")
            text.append(f"{l['text']}\n", style=l['style'])

    return Panel(
        text,
        title="[bold]AGENT EXECUTION & TOOL STREAM[/]",
        border_style="magenta",
        padding=(0, 1)
    )


def build_approval_panel() -> Panel:
    with state._lock:
        pending = list(state.pending_approvals)

    if not pending:
        msg = Text.assemble(
            ("● SYSTEM SECURE  ", "bold green"),
            ("No pending approval requests. Agents operating within safe permissions.", "dim white")
        )
        return Panel(
            Align.center(msg),
            border_style="green",
            style="green"
        )

    # There is an active approval request
    first = pending[0]
    app_id = first.get("approval_id") or first.get("id")
    task_id = first.get("task_id")
    tool = first.get("tool_name")
    args = json.dumps(first.get("arguments", {}))

    alert_text = Text.assemble(
        (" ⚠️  HUMAN APPROVAL REQUIRED! ", "bold black on yellow"),
        (f"  Approval #{app_id} | Task #{task_id}: Agent requests execution of ", "bold white"),
        (f"'{tool}' ", "bold cyan"),
        (f"with args: {args} ", "bright_yellow"),
        ("\n [Action paused waiting for user approval via Mobile App or API] ", "italic white")
    )

    return Panel(
        Align.center(alert_text),
        title="[bold red]SECURITY GATEWAY / HUMAN-IN-THE-LOOP[/]",
        border_style="bold red",
        style="red"
    )


def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=4)
    )

    layout["body"].split_row(
        Layout(name="tasks", ratio=5),
        Layout(name="feed", ratio=6)
    )

    layout["header"].update(build_header_panel())
    layout["tasks"].update(build_tasks_panel())
    layout["feed"].update(build_feed_panel())
    layout["footer"].update(build_approval_panel())

    return layout


def main():
    console = Console()
    console.clear()

    # Parse optional CLI flags
    for i, arg in enumerate(sys.argv):
        if arg == "--server" and i + 1 < len(sys.argv):
            state.server_url = sys.argv[i + 1]
            state.ws_url = state.server_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

    console.print("[cyan]Initializing AI Command Center Terminal Monitor...[/]")
    fetch_initial_data()
    start_background_listener()

    try:
        with Live(make_layout(), console=console, screen=True, refresh_per_second=4) as live:
            while True:
                live.update(make_layout())
                time.sleep(0.25)
    except KeyboardInterrupt:
        console.clear()
        console.print("[yellow]AI Command Center Terminal Monitor terminated.[/]")


if __name__ == "__main__":
    main()
