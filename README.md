# AI Command Center

A local-first control room for AI agents. Point it at your Ollama models, open the
dashboard in your browser, and chat with agents that can actually *do* things — read
your project files, write code, run commands — while you stay in charge of every
sensitive step.

Everything runs on your machine. No cloud, no accounts, no telemetry. If you pull the
plug on your internet, it keeps working.

---

## What it does

**Conversational task workspaces.** Every task is its own thread with a full message
history. Give it a name and a description, then send instructions — the agent remembers
the whole conversation, so follow-ups just work.

**Live token streaming.** Responses stream into the dashboard word by word as the model
thinks them up. No staring at a spinner.

**Real tools, real guardrails.** The agent can list, read, and write files and run shell
commands — but only inside the project directory you allow. Secret files like `.env` are
off-limits entirely, and anything sensitive (writing files, running commands) pauses for
your approval with a security banner before it executes. Deny it, and the agent moves on.

**You're the mission control.** Watch a response go off the rails? Hit **STOP** and it
cancels mid-generation. Finished with a workspace? Mark it done. Done with it forever?
Delete it. Switch between tasks while they're generating and pick up right where you
left off — nothing gets lost.

**Your models, your choice.** Pick any model you've pulled in Ollama per task
(`qwen3.5:9b` for thinking work, `codeqwen:7b` for quick stuff — whatever you have).
Pull a new model and it shows up in the dropdown immediately. And the model answers as
its full self — the Command Center doesn't box it into a persona; tools are extras it
may use, not its identity.

**Real-time everywhere.** A WebSocket stream pushes task updates, logs, tool calls, and
approval requests to every open dashboard instantly. There's also a terminal-native
monitor (`cli_dashboard.py`) if you'd rather watch from a command line.

## Getting started

You'll need:

- **Python 3.10+**
- **[Ollama](https://ollama.com)** running on `http://localhost:11434` with at least one
  model pulled (e.g. `ollama pull qwen3.5:9b`)

Then:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\uvicorn.exe main:app --reload
```

Open **http://127.0.0.1:8000** and create your first task workspace.

> **Lazy?** Double-click **`Start AI Command Center.bat`** in the repo root.
> It starts the backend (in a visible console window), waits until it's up,
> opens the dashboard in your browser, and offers to start the mobile app
> server too. Running it again while the backend is up just opens the dashboard.

> Tip: set `NEBIUS_API_KEY` in `backend/.env` if you ever want to experiment with an
> online provider — the local (Ollama) path needs nothing but Ollama itself.

## Mobile app (React Native + Expo)

A companion app lives in `mobile/` — control and monitor your agents from your
phone over Wi-Fi: dashboard with live activity, streaming chat with your local
models, task management (create / stop / finish / delete), approval decisions,
and configurable server address.

**One-time setup on the PC:**

```powershell
# 1. Run the backend where the phone can reach it (not just localhost):
cd backend
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000

# 2. Let it through Windows Firewall (admin PowerShell, one-time):
netsh advfirewall firewall add rule name="AI Command Center" dir=in action=allow protocol=TCP localport=8000

# 3. Find your PC's Wi-Fi IP (the phone needs this, never 'localhost'):
ipconfig        # → IPv4 Address, e.g. 192.168.1.42
```

**On the phone:**

```powershell
cd mobile
npx expo start          # scan the QR code with the Expo Go app
```

Then in the app: **Settings → PC Server Address** → `http://<your-PC-IP>:8000`
and hit *Test Connection*. Phone and PC must be on the same Wi-Fi. (If the
network blocks device-to-PC traffic, `npx expo start --tunnel`.)

The app reuses the backend's existing REST + WebSocket APIs — nothing extra to
run. If the live stream can't connect, it falls back to 5-second polling.

## How the agent works

Under the hood it's a ReAct loop: the model sees your message (plus the workspace
description as context), and either answers directly or asks for a tool. Tool results
feed back into the conversation, and it keeps going until it has a real answer — capped
at 10 rounds so it can't spiral.

The safety model has three layers:

1. **Sandbox** — every file path is validated against an allowlist before anything
   touches disk. `..\` tricks and paths outside the project are refused.
2. **Secrets blocked** — `.env` and friends can't be read *or* written by the agent.
3. **Human-in-the-loop** — `write_file` and `run_command` pause execution and wait for
   you to click Approve or Deny (in the dashboard or via the API). No approval, no
   execution.

## API quick reference

| Endpoint | What it does |
|---|---|
| `POST /tasks` | Create a workspace (name, description, provider, model) |
| `GET /tasks` | List recent tasks |
| `POST /tasks/{id}/messages` | Send an instruction / follow-up into a task |
| `POST /tasks/{id}/stop` | Cancel a running response (interrupts mid-generation) |
| `POST /tasks/{id}/complete` | Mark a task finished |
| `DELETE /tasks/{id}` | Permanently delete a task and its history |
| `GET /models` | Live list of your installed Ollama models |
| `GET /approvals/pending` | Actions waiting for your decision |
| `POST /approvals/{id}/approve` / `deny` | Decide a pending action |
| `WS /ws` | Real-time event stream (tokens, logs, statuses) |

Full interactive docs live at `http://127.0.0.1:8000/docs` (auto-generated by FastAPI).

## Project layout

```
backend/
├── main.py               # App wiring, dashboard serving
├── database.py           # SQLite repositories (tasks, approvals)
├── models.py             # Pydantic schemas
├── agent/
│   ├── agent.py          # The ReAct loop
│   └── tools.py          # Sandboxed tools + approval flags
├── api/                  # Route modules (chat, tasks, approvals, websocket)
├── providers/            # Ollama (streaming, tool calls) + online stub
├── services/             # Task orchestration, approvals, WS broadcasting
├── static/index.html     # The cyberpunk dashboard
├── cli_dashboard.py      # Terminal-native live monitor
└── test_*.py             # Verification scripts for each subsystem
```

## Running the tests

With the server running (`uvicorn main:app`), from `backend/`:

```powershell
.\venv\Scripts\python.exe test_sandbox.py      # sandbox + secrets blocking
.\venv\Scripts\python.exe test_streaming.py    # provider streaming + tool assembly
.\venv\Scripts\python.exe test_e2e_streaming.py # full stack over WebSocket
.\venv\Scripts\python.exe test_delete.py       # task deletion rules
```

---

Built as a learning project — architecture decisions are commented in the code, so
reading it is half the fun. Enjoy.
