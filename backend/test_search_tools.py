"""
Tests for the new agent tools (search_files, web_search, web_fetch) and the
per-task session logs. Requires the server on 127.0.0.1:8000 for the live
web checks; everything else runs offline.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests

from agent.tools import ToolRegistry, _is_blocked_host

BACKEND = os.path.dirname(os.path.abspath(__file__))
reg = ToolRegistry(allowed_dirs=[BACKEND])

# ── 1. search_files: finds a known string with path:line format ──
r = reg.execute("search_files", {"directory": BACKEND, "query": "MAX_SEARCH_MATCHES"})
assert "tools.py:" in r and "MAX_SEARCH_MATCHES" in r, r[:200]
line = [l for l in r.splitlines() if "tools.py:" in l][0]
assert ": " in line and line.split(":", 2)[1].strip().isdigit()
print("PASS: search_files finds matches with path:line format")

# ── 2. search_files respects the sandbox ──
r = reg.execute("search_files", {"directory": "C:/Windows", "query": "anything"})
assert r.startswith("Permission denied"), r[:100]
print("PASS: search_files refuses paths outside the sandbox")

# ── 3. the .env file itself never appears in search results ──
r = reg.execute("search_files", {"directory": BACKEND, "query": "NEBIUS"})
assert ".env:1:" not in r and not any(l.startswith(".env") for l in r.splitlines()), r[:300]
print("PASS: the .env file is never a search result")

# ── 4. web tools removed — SSRF helpers stay (used by /online/config) ──
from agent.tools import _is_blocked_host, _host_resolves_private
assert "web_search" not in reg._tools and "web_fetch" not in reg._tools
check = _host_resolves_private("localtest.me") and _is_blocked_host("10.0.0.5")
assert check, "SSRF helpers must remain functional"
print("PASS: web tools removed; SSRF helpers still intact for /online/config")

# ── 5. session logs: create -> content -> delete removes file ──
from database import init_db, TaskRepository
from services.session_logger import log_event, delete_session, _files_for
init_db()
repo = TaskRepository()
t = repo.create("session log probe", provider="local")
tid = t.id
log_event(tid, None, "TEST EVENT 1")
log_event(tid, "Probe Name", "TEST EVENT 2")
files = _files_for(tid)
assert files, "session file must exist after log_event"
content = open(files[0], encoding="utf-8").read()
assert "TEST EVENT 1" in content and "TEST EVENT 2" in content
assert content.count("[20") == 2, "each event must be timestamped"
print("PASS: session log created with timestamped entries")

# delete removes exactly that file and leaves others alone
log_event(999999, "Other", "keep me")
before = len(os.listdir(os.path.join(BACKEND, "sessions")))
delete_session(tid)
files_after = _files_for(tid)
assert not files_after, "session file must be deleted with the task"
others = [f for f in _files_for(999999)]
assert others, "unrelated session files must survive"
print("PASS: delete_session removes only the task's file")

# ── 8. tool definitions expose the local tools to the LLM ──
names = [d["function"]["name"] for d in reg.get_definitions()]
assert set(["list_files", "read_file", "search_files", "write_file", "run_command"]).issubset(set(names)), names
assert "web_search" not in names and "web_fetch" not in names
print("PASS: tool definitions correct:", names)

print("\nALL TOOL + SESSION LOG TESTS PASSED")
