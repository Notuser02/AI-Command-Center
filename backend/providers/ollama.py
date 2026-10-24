import json
import threading

import requests


class OllamaProvider:

    def __init__(self, model="qwen3.5:9b"):
        self.model = model
        self.base_url = "http://localhost:11434"
        # The currently-streaming HTTP response (if any). Kept so cancel()
        # can close it from another thread and interrupt generation instantly.
        self._active_response = None
        self._response_lock = threading.Lock()

    @classmethod
    def list_models(cls, base_url="http://localhost:11434"):
        """Query Ollama API for all installed models on this PC."""
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return ["qwen3.5:9b"]

    def generate(self, prompt):
        """Simple prompt → text. Used by the /chat endpoint."""
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        result = response.json()

        return result["response"]

    def chat(self, messages, tools=None, on_token=None):
        """
        Conversation-style call with optional tool definitions.
        Used by the Agent for multi-step tool-calling loops.

        Args:
            messages: list of {"role": "...", "content": "..."}
            tools:    list of tool definitions (OpenAI format), or None
            on_token: optional callback(str). If provided, the response is
                      STREAMED and the callback fires for every text chunk
                      as it arrives. The final assembled message is still
                      returned, in the same shape as non-streaming mode:
                      {"role": "assistant", "content": "..."} or
                      {"role": "assistant", "content": "", "tool_calls": [...]}

        Why a callback instead of returning a generator?
          The Agent runs inside a worker thread and already uses callbacks
          for progress updates — a callback matches that style, and the
          method can still `return` the final message normally.
        """
        if on_token is None:
            return self._chat_blocking(messages, tools)
        return self._chat_streaming(messages, tools, on_token)

    def _build_payload(self, messages, tools, stream):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        if tools:
            payload["tools"] = tools
            # Qwen3.5 has a "thinking" mode that wraps reasoning in <think> tags.
            # This conflicts with tool calling — the model can produce empty output
            # (no text AND no tool calls), which Ollama rejects.
            # Setting think=False disables this so tool calls work reliably.
            payload["think"] = False
        return payload

    def _chat_blocking(self, messages, tools=None):
        """Original non-streaming request (unchanged behavior)."""
        payload = self._build_payload(messages, tools, stream=False)

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload
        )

        result = response.json()

        # If Ollama returns an error (e.g. model does not support tools)
        if response.status_code != 200:
            err_text = result.get("error", "")
            if "does not support tools" in err_text and "tools" in payload:
                payload.pop("tools", None)
                payload.pop("think", None)
                retry_response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
                retry_result = retry_response.json()
                if retry_response.status_code == 200 and "message" in retry_result:
                    return retry_result["message"]
                raise RuntimeError(f"Ollama error on fallback: {retry_result.get('error', retry_response.text)}")
            raise RuntimeError(f"Ollama error: {err_text or response.text}")

        if "message" not in result:
            raise RuntimeError(f"Ollama response missing 'message': {result}")

        return result["message"]

    def _chat_streaming(self, messages, tools, on_token):
        """
        Streamed request: text chunks go to on_token() as they arrive,
        and everything is assembled back into the same message dict
        the blocking path returns.
        """
        payload = self._build_payload(messages, tools, stream=True)

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=(5, 600)  # (connect, read): generous read timeout —
                              # chunks arrive continuously during generation
        )

        if response.status_code != 200:
            # Errors (e.g. "model does not support tools") arrive as a normal
            # JSON body, not as a stream — degrade like the blocking path does.
            try:
                err_text = response.json().get("error", "")
            except ValueError:
                err_text = response.text
            if "does not support tools" in err_text and tools:
                return self._chat_blocking(messages, tools=None)
            raise RuntimeError(f"Ollama error: {err_text or response.text}")

        # Register the stream so cancel() can close it mid-generation
        with self._response_lock:
            self._active_response = response

        content_parts = []
        tool_calls = []
        stream_error = None

        try:
            # Ollama streams newline-delimited JSON objects, one per token/chunk
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Streaming errors arrive as {"error": "..."} chunks
                if "error" in chunk:
                    stream_error = chunk["error"]
                    break

                msg = chunk.get("message", {})

                delta = msg.get("content") or ""
                if delta:
                    content_parts.append(delta)
                    on_token(delta)

                if msg.get("tool_calls"):
                    self._merge_tool_call_fragments(tool_calls, msg["tool_calls"])
        finally:
            # Un-register (also runs when abort() closed the stream under us
            # and iter_lines raised)
            with self._response_lock:
                if self._active_response is response:
                    self._active_response = None
            response.close()

        if stream_error:
            # e.g. this model can't do native tool calling — degrade
            # exactly like the blocking path does (plain chat, no tools)
            if "does not support tools" in stream_error and tools:
                return self._chat_blocking(messages, tools=None)
            raise RuntimeError(f"Ollama stream error: {stream_error}")

        message = {"role": "assistant", "content": "".join(content_parts)}

        if tool_calls:
            # Safety net: if fragment assembly produced an unnamed call,
            # the stream format was something we didn't understand.
            # Re-ask once without streaming to get an authoritative answer.
            if any(not call["function"].get("name") for call in tool_calls):
                return self._chat_blocking(messages, tools)
            message["tool_calls"] = tool_calls

        return message

    def abort(self):
        """
        Interrupt an in-flight streaming request from another thread.
        Closing the response makes the blocked read inside _chat_streaming
        raise immediately, so a cancelled agent stops mid-generation
        instead of grinding through the rest of the answer.
        Safe to call anytime; no-op when nothing is streaming.
        """
        with self._response_lock:
            resp = self._active_response
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    @staticmethod
    def _merge_tool_call_fragments(accumulated, fragments):
        """
        Streamed tool calls arrive in PIECES. Two formats exist depending
        on Ollama version:

          New:  each fragment carries an "index" telling us which call it
                belongs to (name pieces and argument pieces arrive separately).
          Old:  complete tool_calls arrive in one chunk with no index.

        This merger handles both: names concatenate, argument keys fill in
        (string values may themselves arrive split across chunks).
        """
        for frag in fragments:
            func = frag.get("function") or {}
            index = frag.get("index")

            if index is None:
                # Old format or single complete call: if the name matches a
                # call we've already seen, merge into it; otherwise append.
                name = func.get("name") or ""
                if name:
                    index = next(
                        (i for i, c in enumerate(accumulated)
                         if c["function"].get("name") == name),
                        len(accumulated)
                    )
                else:
                    index = len(accumulated) - 1 if accumulated else 0

            while len(accumulated) <= index:
                accumulated.append({"function": {"name": "", "arguments": {}}})

            target = accumulated[index]["function"]

            if func.get("name"):
                target["name"] = (target.get("name") or "") + func["name"]

            args = func.get("arguments")
            if args:
                # Some versions send arguments as a JSON string
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        continue
                if isinstance(args, dict):
                    for key, value in args.items():
                        if (key in target["arguments"]
                                and isinstance(value, str)
                                and isinstance(target["arguments"][key], str)):
                            # string value split across chunks → concatenate
                            target["arguments"][key] += value
                        else:
                            target["arguments"][key] = value


if __name__ == "__main__":
    provider = OllamaProvider()

    answer = provider.generate("Explain what an API is in one sentence.")

    print(answer)
