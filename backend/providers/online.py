"""
OnlineProvider — any OpenAI-compatible API as an online model backend.

Works with Nebius, OpenRouter, Groq, OpenAI, DeepSeek, Mistral, Together…
(anything exposing POST {base}/chat/completions). Configuration (base URL +
API key + default model) lives in the settings table, edited via the
dashboard / phone Settings — see api/online.py.

Two jobs here beyond plain HTTP:
  1. FORMAT ADAPTER — the agent loop speaks Ollama-style messages
     (tool arguments as dicts, tool results as bare {role:"tool", content});
     OpenAI-style APIs want tool_call ids and JSON-string arguments. The
     _to_openai/_from_openai functions translate both ways so the agent,
     approvals, and sandbox work unchanged.
  2. STREAMING + ABORT — SSE chunks stream tokens to on_token (live output
     in the dashboard/phone) and abort() closes the connection so STOP
     interrupts mid-generation, exactly like the Ollama provider.
"""

import json
import threading
import requests


class OnlineProvider:

    def __init__(self, base_url: str, api_key: str, model: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self._active_response = None
        self._response_lock = threading.Lock()

    # ── configuration ─────────────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def list_models(self, timeout: float = 10.0):
        """GET {base}/models — the service's live model list."""
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Could not reach {self.base_url} — check the base URL")
        except requests.exceptions.Timeout:
            raise RuntimeError(f"{self.base_url} timed out")

        if resp.status_code in (401, 403):
            raise RuntimeError("Invalid API key (the service rejected it)")
        if resp.status_code != 200:
            raise RuntimeError(f"Service error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        # OpenAI shape: {data: [{id}]}; some services: {models: [{name}]}
        items = data.get("data") or data.get("models") or []
        names = [m.get("id") or m.get("name") for m in items if isinstance(m, dict)]
        return [n for n in names if n]

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    # ── chat (agent-facing, same contract as OllamaProvider) ───────

    def chat(self, messages, tools=None, on_token=None):
        if not self.is_configured():
            return {
                "role": "assistant",
                "content": "Online provider is not configured — add an API key in Settings "
                           "(or the task creation dialog on the PC dashboard).",
            }

        payload = {
            "model": self.model,
            "messages": self._to_openai(messages),
            "stream": on_token is not None,
        }
        if tools:
            payload["tools"] = tools

        if on_token is not None:
            return self._chat_streaming(payload, on_token)
        return self._chat_blocking(payload)

    def _chat_blocking(self, payload):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=(5, 600),
            )
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Could not reach {self.base_url} — check the base URL")

        if resp.status_code in (401, 403):
            raise RuntimeError("Invalid API key (the service rejected it)")
        if resp.status_code != 200:
            raise RuntimeError(f"Service error {resp.status_code}: {resp.text[:300]}")

        message = resp.json()["choices"][0]["message"]
        return self._from_openai(message)

    def _chat_streaming(self, payload, on_token):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=(5, 600),
            )
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Could not reach {self.base_url} — check the base URL")

        if resp.status_code in (401, 403):
            raise RuntimeError("Invalid API key (the service rejected it)")
        if resp.status_code != 200:
            raise RuntimeError(f"Service error {resp.status_code}: {resp.text[:300]}")

        with self._response_lock:
            self._active_response = resp

        content_parts = []
        tool_calls = []  # [{id, function: {name, arguments-str}}]
        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                data_str = raw_line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                text = delta.get("content") or ""
                if text:
                    content_parts.append(text)
                    on_token(text)

                for frag in delta.get("tool_calls") or []:
                    self._merge_streamed_tool_call(tool_calls, frag)
        finally:
            with self._response_lock:
                if self._active_response is resp:
                    self._active_response = None
            resp.close()

        return self._from_openai({
            "content": "".join(content_parts),
            "tool_calls": [
                {"id": tc["id"], "function": tc["function"]}
                for tc in tool_calls if tc["function"].get("name")
            ],
        })

    @staticmethod
    def _merge_streamed_tool_call(accumulated, frag):
        """OpenAI streams tool calls as fragments with an index."""
        index = frag.get("index") or 0
        while len(accumulated) <= index:
            accumulated.append({"id": "", "function": {"name": "", "arguments": ""}})
        target = accumulated[index]
        if frag.get("id"):
            target["id"] = frag["id"]
        fn = frag.get("function") or {}
        if fn.get("name"):
            target["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            target["function"]["arguments"] += fn["arguments"]  # JSON string pieces

    def abort(self):
        """Interrupt an in-flight stream (STOP button) from another thread."""
        with self._response_lock:
            resp = self._active_response
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    # ── format adapters ───────────────────────────────────────────

    @staticmethod
    def _to_openai(messages):
        """Agent format → OpenAI format. The agent's tool-result messages
        ({role:"tool", content}) need the tool_call_id of the call they
        answer, so we attach ids while converting assistant messages."""
        out = []
        pending_ids = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": pending_ids.pop(0) if pending_ids else "call_0",
                    "content": msg.get("content", ""),
                })
                continue

            converted = {"role": role, "content": msg.get("content") or ""}
            calls = msg.get("tool_calls")
            if calls:
                openai_calls = []
                pending_ids = []
                for i, call in enumerate(calls):
                    call_id = call.get("id") or f"call_{len(out)}_{i}"
                    fn = call.get("function") or {}
                    args = fn.get("arguments", {})
                    if not isinstance(args, str):
                        args = json.dumps(args)
                    openai_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {"name": fn.get("name", ""), "arguments": args},
                    })
                    pending_ids.append(call_id)
                converted["tool_calls"] = openai_calls
                if not converted["content"]:
                    converted["content"] = None
            out.append(converted)
        return out

    @staticmethod
    def _from_openai(message):
        """OpenAI message → agent format (tool arguments become dicts)."""
        converted = {"role": "assistant", "content": message.get("content") or ""}
        calls = message.get("tool_calls")
        if calls:
            agent_calls = []
            for call in calls:
                fn = call.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                agent_calls.append({
                    "id": call.get("id"),
                    "type": "function",
                    "function": {"name": fn.get("name", ""), "arguments": args or {}},
                })
            converted["tool_calls"] = agent_calls
        return converted
