<div align="center">

# 🕹 AI Command Center

## Create · Deploy · Monitor — From Anywhere

*A local-first, privacy-focused AI agent workstation: run autonomous agents on your own PC with your own Ollama models, watch them work in real time, and stay in control from your browser or phone.*

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/LLMs-Ollama_Local-black?logo=ollama&logoColor=white)
![Mobile](https://img.shields.io/badge/Mobile-Expo_+_React_Native-000020?logo=expo&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)

[Quick Start](#-quick-start) · [What It Does](#-what-it-does) · [Mobile App](#-mobile-app-react-native--expo) · [Remote Access](#-remote-access-tailscale) · [Safety](#-safety) · [API](#%EF%B8%8F-api-quick-reference) · [Project Layout](#-project-layout)

</div>

---

## 🚀 Quick Start

**What you need first (once):**

- **Windows 10/11** with [Python 3.10+](https://python.org) (tick *"Add python.exe to PATH"* in its installer)
- **[Ollama](https://ollama.com)** installed, with at least one model — `ollama pull qwen3.5:9b` works great (any model you like is fine)
- Optional: **[Node.js 18+](https://nodejs.org)** — only if you want the phone app
- Optional: **[Tailscale](https://tailscale.com)** — if you want phone access away from home

**Setup (once):**

```powershell
git clone https://github.com/Notuser02/AI-Command-Center.git
cd AI-Command-Center\backend
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

Optional extras:

- **Let the agent reach more folders** (by default it only sees the `backend/` folder):
  copy `backend\allowed_dirs.example.txt` → `backend\allowed_dirs.txt` and list your folders, one per line
- **Use an online provider** instead of local models: create `backend\.env` containing `ONLINE_API_KEY=...`

**Run it (every time):**

> Double-click **`Start AI Command Center.bat`** in the repo root. It starts Ollama and the
> backend in visible console windows, waits until both are ready, and opens the dashboard
> in your browser. Running it again while it's up just opens the dashboard.

Or manually, in two terminals:

```powershell
ollama serve                                                   # terminal 1 — model server
cd backend
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 # terminal 2 — backend
# → open http://127.0.0.1:8000
```

**Stop:** close the *"AI Command Center Backend"* and *"Ollama Server"* console windows.

**Phone app (build once, then install from your browser):**

```powershell
cd mobile
npm install
npm run export:web          # builds the app into the backend

# one-time, admin PowerShell — let phones reach port 8000:
netsh advfirewall firewall add rule name="AI Command Center" dir=in action=allow protocol=TCP localport=8000

ipconfig                     # note your PC's IPv4 (Wi-Fi adapter)
```

Then on the phone (same Wi-Fi): open **`http://<your-PC-IP>:8000/m`** in Chrome →
menu (⋮) → **Install app**. Away from home, see [Remote Access](#-remote-access-tailscale) below.

**Troubleshooting**

| Symptom | Check |
|---|---|
| Agents don't answer | Is the *Ollama Server* window running? (`ollama serve`) |
| Page won't open | Is the *AI Command Center Backend* window running? |
| Phone can't connect | Same Wi-Fi (or Tailscale ON)? Firewall rule added? Backend window open? |
| Port 8000 already in use | An old backend window is still open — close it first |

---

## ✨ What It Does

**Agents that actually do things** — not chat windows. Each task is a workspace where the agent can inspect real files, write code, and run commands to finish the job.

- **Token streaming everywhere:** responses stream live into the dashboard and phone, word by word — no spinners.
- **Real tools, real guardrails:** `list_files`, `read_file`, `search_files` (grep), `write_file`, `run_command`, `web_search`, `web_fetch` — file tools sandboxed to folders *you* allowlist, web tools locked to the public internet (internal/private addresses refused), and sensitive actions paused until **you** click Approve.
- **You're mission control:** STOP cancels mid-generation (aborting the model mid-answer, not after it finishes), FINISH archives, DELETE removes — from the dashboard or your phone.
- **The model stays itself:** no confining persona — ask "what can you do?" and the model answers with its full capabilities, tools as optional extras.
- **Real-time by construction:** a WebSocket stream pushes every token, tool call, status change, and approval request to all connected clients instantly.
- **Switch tasks mid-response:** streams buffer per-task, so flipping between running agents and back loses nothing.

---

## 📱 Mobile App (React Native + Expo)

A full companion app in `mobile/` — **Dashboard** (connection, models, task stats, approvals, live feed), **Chat** (streaming conversations with your local models), **Tasks** (create / monitor / stop / finish / delete), and **Settings** — all talking to your PC's backend over Wi-Fi.

**One-time PC setup:**

```powershell
# backend must listen on the LAN + be allowed through the firewall (admin):
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000
netsh advfirewall firewall add rule name="AI Command Center" dir=in action=allow protocol=TCP localport=8000
ipconfig        # note your PC's IPv4 (Wi-Fi adapter)
```

**Phone:** install **Expo Go**, same Wi-Fi, then from `mobile/`:

```powershell
npx expo start          # scan the QR code
```

In the app: **Settings → PC Server Address** → `http://<your-PC-IP>:8000` → *Test Connection*. Never `localhost` — on a phone that means the phone itself.

## 🌐 Online Models (bring your own API key)

Any OpenAI-compatible service works — **Nebius, OpenRouter, Groq, OpenAI,
DeepSeek**, Mistral, Together… Set it up once:

1. In the task creation dialog (PC) switch Provider to **Online** → *Add / Manage
   API key* — or on the phone, **Settings → Online Provider**
2. Pick a preset (or paste any base URL) and paste your API key → **Test & Save**
3. The service's live model list fills the model dropdown automatically

Your key is stored only on your PC (in the local database — never in git, never
returned by the API). Online tasks stream token-by-token and support STOP exactly
like local models; the agent's tools, sandbox, and approvals work unchanged.

---

## 🌍 Remote Access (Tailscale)

Wi-Fi is for home. For anywhere-access, use [Tailscale](https://tailscale.com) (free) — a private encrypted network between *your* devices only. The public internet sees nothing, so the backend needs no passwords; the network itself is lock and key.

1. **PC:** install Tailscale (`winget install Tailscale.Tailscale`) and sign in
2. **Phone:** install the Tailscale app, sign in with the **same account**, toggle it ON
3. **On the phone:** open `https://<your-pc>.ts.net/m` and Chrome's menu → **Install app** — the mobile app installs as a real PWA (icon, full-screen, auto-updating)
   - the HTTPS address comes from `tailscale serve` on the PC: `tailscale serve --bg http://127.0.0.1:8000`
   - without HTTPS, `http://<100.x.y.z>:8000/m` works too (Add to Home screen)

Works over mobile data, campus Wi-Fi, anywhere. ⚠️ Don't expose the backend with port-forwarding or public tunnels instead — it has no authentication layer by design, because only your tailnet can reach it.

---

## 🔒 Safety

Three layers, all enforced server-side:

1. **Path sandbox:** every file path is validated against an allowlist (`backend/allowed_dirs.txt` — one folder per line, see `allowed_dirs.example.txt`; by default only the project folder itself) before anything touches disk. `..\` tricks and outside paths are refused.
2. **Secrets blocked:** `.env`-style files can't be read *or* written by the agent — anywhere.
3. **Human-in-the-loop:** `write_file` and `run_command` pause execution and wait for Approve/Deny — from the dashboard, the phone, or the API. No approval, no execution.
4. **Web tools stay outside:** `web_search` (DuckDuckGo, Bing fallback) and `web_fetch` are read-only, keyless, and refuse internal/private addresses (localhost, LAN, Tailscale) — your PC can't be probed through them, and only the query text ever leaves the machine.
5. **Session journals:** every task writes a plain-text log to `backend/sessions/` (created, messages, tool calls, statuses) — deleted automatically with the task, gitignored, a few KB each.

---

## 🛠️ API Quick Reference

| Endpoint | What it does |
|---|---|
| `POST /tasks` | Create a workspace (name, description, provider, model) |
| `GET /tasks` | List recent tasks |
| `POST /tasks/{id}/messages` | Send an instruction / follow-up (agent turn) |
| `POST /tasks/{id}/stop` | Cancel — interrupts mid-generation |
| `POST /tasks/{id}/complete` | Archive a finished conversation |
| `DELETE /tasks/{id}` | Permanently delete (refuses while running) |
| `GET /models` | Live list of installed Ollama models |
| `GET /approvals/pending` | Sensitive actions awaiting your decision |
| `POST /approvals/{id}/approve` / `deny` | Decide them |
| `WS /ws` | Real-time events: tokens, logs, statuses, approvals |

Interactive docs at `http://127.0.0.1:8000/docs` (auto-generated by FastAPI).

---

## 📁 Project Layout

```
backend/
├── main.py               # App wiring + launcher entry
├── database.py           # SQLite repositories (tasks, approvals)
├── agent/
│   ├── agent.py          # The ReAct loop
│   └── tools.py          # Sandboxed tools + approval flags
├── api/                  # Route modules (chat, tasks, approvals, websocket)
├── providers/            # Ollama (streaming + tool calls), online stub
├── services/             # Task orchestration, approvals, WS broadcasting
├── static/index.html     # The cyberpunk web dashboard
├── cli_dashboard.py      # Terminal-native live monitor
└── test_*.py             # Per-subsystem verification scripts
mobile/                   # Expo + React Native companion app
Start AI Command Center.bat   # one-click launcher (Ollama + backend + browser)
```

---

## ✅ Tests

With the backend running, from `backend/`:

```powershell
.\venv\Scripts\python.exe test_sandbox.py        # sandbox + secrets blocking
.\venv\Scripts\python.exe test_streaming.py      # provider streaming + tool assembly
.\venv\Scripts\python.exe test_e2e_streaming.py  # full stack over WebSocket
.\venv\Scripts\python.exe test_delete.py         # task deletion rules
```
