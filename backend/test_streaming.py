"""Verify OllamaProvider streaming against the live Ollama server."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers.ollama import OllamaProvider

BACKEND = os.path.dirname(os.path.abspath(__file__))

# ── 1. Plain streaming: tokens arrive incrementally, final matches ──
p = OllamaProvider(model="qwen3.5:9b")
tokens = []
msg = p.chat(
    [{"role": "user", "content": "Say exactly: STREAMING WORKS. Nothing else."}],
    on_token=tokens.append,
)
assert len(tokens) > 1, f"expected multiple tokens, got {len(tokens)}"
assert msg["content"] == "".join(tokens), "final content must equal joined tokens"
assert not msg.get("tool_calls")
print(f"PASS: plain streaming — {len(tokens)} tokens, final content matches")

# ── 2. Streamed tool call assembles correctly ──
tools = [{
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files and folders in a directory.",
        "parameters": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
}]
tokens2 = []
msg2 = p.chat(
    [{"role": "user", "content": f"List the files in the directory {BACKEND}. Use the tool."}],
    tools=tools,
    on_token=tokens2.append,
)
calls = msg2.get("tool_calls")
assert calls, f"expected tool_calls, got: {msg2}"
for c in calls:
    assert c["function"]["name"], f"unnamed tool call: {c}"
    assert isinstance(c["function"].get("arguments"), dict)
print("PASS: streamed tool call assembled ->",
      [(c['function']['name'], c['function']['arguments']) for c in calls])

# ── 3. codeqwen (no native tools): graceful fallback while streaming ──
pq = OllamaProvider(model="codeqwen:7b")
tokens3 = []
msg3 = pq.chat(
    [{"role": "user", "content": "Reply with exactly: FALLBACK OK"}],
    tools=tools,
    on_token=tokens3.append,
)
assert msg3.get("content"), f"fallback produced no content: {msg3}"
print(f"PASS: codeqwen tools-fallback while streaming -> content: {msg3['content'][:50]!r}")

print("\nALL STREAMING TESTS PASSED")
