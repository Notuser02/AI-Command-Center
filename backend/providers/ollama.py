import requests


class OllamaProvider:

    def __init__(self, model="qwen3.5:9b"):
        self.model = model
        self.base_url = "http://localhost:11434"

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

    def chat(self, messages, tools=None):
        """
        Conversation-style call with optional tool definitions.
        Used by the Agent for multi-step tool-calling loops.

        Args:
            messages: list of {"role": "...", "content": "..."}
            tools:    list of tool definitions (OpenAI format), or None

        Returns:
            The assistant's message dict, e.g.:
            {"role": "assistant", "content": "..."} or
            {"role": "assistant", "content": "", "tool_calls": [...]}
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }

        if tools:
            payload["tools"] = tools
            # Qwen3.5 has a "thinking" mode that wraps reasoning in <think> tags.
            # This conflicts with tool calling — the model can produce empty output
            # (no text AND no tool calls), which Ollama rejects.
            # Setting think=False disables this so tool calls work reliably.
            payload["think"] = False

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload
        )

        result = response.json()

        return result["message"]


if __name__ == "__main__":
    provider = OllamaProvider()

    answer = provider.generate("Explain what an API is in one sentence.")

    print(answer)