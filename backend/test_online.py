"""
Tests for the online provider feature (config storage, endpoint behavior,
and the message-format adapters). Requires the server on 127.0.0.1:8000.

Uses a deliberately unreachable base URL — this exercises validation and
error paths without needing a real API key.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests

HTTP = "http://127.0.0.1:8000"

# ── 1. GET /online/config — never leaks the key ──
cfg = requests.get(f"{HTTP}/online/config", timeout=10).json()
assert set(cfg.keys()) == {"base_url", "api_key_set", "default_model"}, cfg
print("PASS: GET /online/config returns only safe fields:", cfg)

# ── 2. POST with an unreachable base URL → clean 400, NOTHING saved ──
r = requests.post(f"{HTTP}/online/config", json={
    "base_url": "http://127.0.0.1:9/v1",
    "api_key": "sk-test-fake-key",
}, timeout=30)
assert r.status_code == 400, (r.status_code, r.text)
assert "Could not reach" in r.json()["detail"] or "timed out" in r.json()["detail"], r.text
cfg = requests.get(f"{HTTP}/online/config", timeout=10).json()
assert cfg["api_key_set"] is False and cfg["base_url"] == "", "failed save must not persist!"
print("PASS: unreachable base URL → 400, and nothing was saved")

# ── 3. POST with an invalid key against a real service → 400 invalid key ──
r = requests.post(f"{HTTP}/online/config", json={
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-invalid-test-key-12345",
}, timeout=30)
assert r.status_code == 400, (r.status_code, r.text)
cfg = requests.get(f"{HTTP}/online/config", timeout=10).json()
assert cfg["api_key_set"] is False and cfg["base_url"] == "", "failed save must not persist!"
print("PASS: bad key against real service → 400, nothing saved")

# ── 4. Cleanup: reset config to empty (settings repo direct) ──
from database import init_db, SettingsRepository
init_db()
repo = SettingsRepository()
repo.delete("online_base_url")
repo.delete("online_api_key")
repo.delete("online_default_model")
cfg = requests.get(f"{HTTP}/online/config", timeout=10).json()
assert cfg == {"base_url": "", "api_key_set": False, "default_model": ""}, cfg
print("PASS: config reset to clean state")

# ── 5. /models has empty online list when unconfigured ──
models = requests.get(f"{HTTP}/models", timeout=10).json()
assert models["online"] == [], models["online"]
assert len(models["local"]) > 0
print("PASS: /models.online empty when unconfigured, local intact")

# ── 6. Message-format adapters (unit) ──
from providers.online import OnlineProvider
msgs = [
    {"role": "system", "content": "s"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "list_files", "arguments": {"directory": "C:/"}}}]},
    {"role": "tool", "content": "file1"},
]
out = OnlineProvider._to_openai(msgs)
assert isinstance(out[2]["tool_calls"][0]["function"]["arguments"], str)
assert out[3]["tool_call_id"] == out[2]["tool_calls"][0]["id"]
back = OnlineProvider._from_openai({
    "content": "ok",
    "tool_calls": [{"id": "x", "function": {"name": "read_file",
                                              "arguments": '{"file_path": "a"}'}}],
})
assert back["tool_calls"][0]["function"]["arguments"] == {"file_path": "a"}
print("PASS: OpenAI format adapters round-trip correctly")

print("\nALL ONLINE PROVIDER TESTS PASSED")
