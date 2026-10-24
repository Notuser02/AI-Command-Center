"""Quick verification of the new tool sandbox rules (run manually)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.tools import ToolRegistry

BACKEND = os.path.dirname(os.path.abspath(__file__))
reg = ToolRegistry(allowed_dirs=[BACKEND])

# 1. Sensitivity flags
assert not reg.requires_approval("list_files")
assert not reg.requires_approval("read_file")
assert reg.requires_approval("write_file"), "write_file must require approval"
assert reg.requires_approval("run_command")
print("PASS: sensitivity flags (write_file + run_command gated)")

# 2. .env is blocked for reading
r = reg.execute("read_file", {"file_path": os.path.join(BACKEND, ".env")})
assert r.startswith("Permission denied"), r
print("PASS: read_file refuses .env ->", r[:60])

# 3. .env is blocked for writing
r = reg.execute("write_file", {"file_path": os.path.join(BACKEND, ".env"), "content": "x"})
assert r.startswith("Permission denied"), r
print("PASS: write_file refuses .env")

# 4. Outside sandbox blocked
r = reg.execute("write_file", {"file_path": "C:/Windows/stolen.txt", "content": "x"})
assert r.startswith("Permission denied"), r
print("PASS: write_file refuses paths outside sandbox")

# 5. Legit write + read-back inside sandbox (new subfolder)
target = os.path.join(BACKEND, "__sandbox_test__", "hello.txt")
r = reg.execute("write_file", {"file_path": target, "content": "line1\nline2\n"})
assert r.startswith("OK: wrote"), r
back = reg.execute("read_file", {"file_path": target})
assert back == "line1\nline2\n", repr(back)
print("PASS: write_file creates files and read_file reads them back")

# 6. Tool definition present for the LLM
defs = reg.get_definitions()
names = [d["function"]["name"] for d in defs]
assert "write_file" in names, names
print("PASS: write_file exposed to LLM:", names)

# cleanup
import shutil
shutil.rmtree(os.path.join(BACKEND, "__sandbox_test__"), ignore_errors=True)

# 7. Stale-task recovery
from database import init_db, TaskRepository
init_db()
repo = TaskRepository()
t = repo.create("stale recovery probe", provider="local")
repo.update_status(t.id, "running" and __import__("models").TaskStatus.RUNNING)
fixed = repo.reset_stale_running()
after = repo.get(t.id)
assert after.status == "failed", after.status
print(f"PASS: reset_stale_running fixed {fixed} row(s), probe task now '{after.status}'")

print("\nALL TOOL/SANDBOX TESTS PASSED")
