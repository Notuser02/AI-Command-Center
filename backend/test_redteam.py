"""
RED-TEAM PROBE — attacks our own defenses. Run against the ToolRegistry and
web tools directly (offline-safe except where noted). Every FAIL = a hole.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.tools import ToolRegistry, _is_blocked_host

BACKEND = os.path.dirname(os.path.abspath(__file__))
reg = ToolRegistry(allowed_dirs=[BACKEND])
fails = []

def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)

# ── 1. Path traversal via read_file ──
traversals = [
    "../../Windows/win.ini",
    "..\\..\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "C:\\Windows\\win.ini",
    f"{BACKEND}/../../Windows/win.ini",
    f"{BACKEND}\\..\\..\\Windows\\win.ini",
    "....//....//Windows/win.ini",
]
for t in traversals:
    r = reg.execute("read_file", {"file_path": t})
    check(f"traversal blocked: {t[:45]}", r.startswith("Permission denied") or r.startswith("Error:"), r[:60])

# ── 2. Secrets ──
r = reg.execute("read_file", {"file_path": os.path.join(BACKEND, ".env")})
check(".env read blocked", r.startswith("Permission denied"), r[:60])
r = reg.execute("write_file", {"file_path": os.path.join(BACKEND, ".env"), "content": "X=1"})
check(".env write blocked", r.startswith("Permission denied"), r[:60])
r = reg.execute("write_file", {"file_path": os.path.join(BACKEND, "..", ".env"), "content": "X=1"})
check("parent .env write blocked", r.startswith("Permission denied"), r[:60])

# ── 3. write_file traversal ──
r = reg.execute("write_file", {"file_path": "C:/Windows/acc_test.txt", "content": "x"})
check("write outside blocked", r.startswith("Permission denied"), r[:60])
r = reg.execute("write_file", {"file_path": f"{BACKEND}/../../acc_test.txt", "content": "x"})
check("write traversal blocked", r.startswith("Permission denied"), r[:60])

# ── 4. search_files refuses outside + skips secrets ──
r = reg.execute("search_files", {"directory": "C:/Windows", "query": "x"})
check("search outside blocked", r.startswith("Permission denied"), r[:60])

# ── 5. internal data stores must be unreadable ──
r = reg.execute("read_file", {"file_path": os.path.join(BACKEND, "tasks.db")})
check("tasks.db read blocked", r.startswith("Permission denied"), r[:60])
sess = os.path.join(BACKEND, "sessions")
if os.path.isdir(sess):
    files = os.listdir(sess)
    if files:
        r = reg.execute("read_file", {"file_path": os.path.join(sess, files[0])})
        check("session journal read blocked", r.startswith("Permission denied"), r[:60])
    else:
        print("INFO no session files present to test")
r = reg.execute("search_files", {"directory": BACKEND, "query": "AGENT ANSWER"})
assert not any(l.startswith("sessions") for l in r.splitlines())
check("search skips sessions dir", True)

# ── 6. SSRF host defenses (layered) ──
# String-level tricks must be caught by the fast hostname check:
for host in ["2130706433", "0x7f000001", "127.1", "[::1]", "::ffff:127.0.0.1"]:
    check(f"blocklist catches: {host}", _is_blocked_host(host))
# DNS names that resolve to private IPs are caught by the RESOLUTION check:
from agent.tools import _host_resolves_private
for host in ["127.0.0.1.nip.io", "localtest.me"]:
    check(f"resolver catches: {host}", _host_resolves_private(host))
for host in ["example.com", "pypi.org"]:
    check(f"resolver allows public: {host}", not _host_resolves_private(host))

# private ranges must stay blocked, public stay allowed
for host in ["10.3.39.142", "192.168.56.1", "172.20.0.5", "100.118.150.53"]:
    check(f"private stays blocked: {host}", _is_blocked_host(host))
for host in ["example.com", "8.8.8.8", "pypi.org"]:
    check(f"public stays allowed: {host}", not _is_blocked_host(host))

# ── 7. live web_fetch SSRF attempts (needs internet for DNS) ──
for url, why in [
    ("http://127.0.0.1:8000/status", "loopback"),
    ("http://2130706433:8000/status", "decimal loopback"),
    ("http://127.0.0.1.nip.io:8000/status", "DNS-to-loopback"),
    ("http://100.118.150.53:8000/status", "own tailscale IP"),
]:
    r = reg.execute("web_fetch", {"url": url})
    check(f"web_fetch blocked: {why}", "not allowed" in r or "Error" in r, r[:70])

print()
print("RESULT:", "ALL CLEAR" if not fails else f"{len(fails)} HOLE(S): {fails}")
