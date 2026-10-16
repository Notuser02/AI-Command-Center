"""
The Agent: the brain of the AI Command Center.

EVOLUTION:
  Before:  Task → LLM → Answer  (single shot)
  Now:     Task → LLM → [Tool? → Result → LLM →]* → Answer  (loop)

KEY CONCEPT: The "ReAct loop"
  1. Agent sends the task + tool descriptions to the LLM
  2. LLM either answers directly OR requests a tool call
  3. If tool call: agent runs the tool, sends result back to LLM
  4. Repeat until LLM gives a final text answer (or we hit a safety limit)

The Agent stays provider-agnostic — it calls self.provider.chat()
and doesn't care whether that goes to Ollama, Nebius, or anything else.
"""

import json
import threading
import asyncio


# Maximum tool-call rounds before we force-stop.
# Prevents infinite loops if the LLM keeps calling tools forever.
MAX_TOOL_ROUNDS = 10


class CancellationError(Exception):
    """Raised when the agent is cancelled during execution."""
    pass


class Agent:

    def __init__(self, provider, tool_registry=None):
        self.provider = provider
        self.tool_registry = tool_registry
        self.status = "idle"
        self.result = None
        self.logs = []      # step-by-step record of what the agent did
        self._cancel_event = threading.Event()

    def run(self, task):
        self.status = "running"
        self.logs = []
        self._cancel_event.clear()

        try:
            # ── No tools? Use the old simple path (backward compatible) ──
            if not self.tool_registry:
                self.result = self.provider.generate(task)
                self.status = "completed"
                return self.result

            # ── Tool-calling loop ────────────────────────────────────
            result = self._run_with_tools(task)
            self.status = "completed"
            return result

        except CancellationError:
            self.status = "cancelled"
            self.logs.append({"step": "cancelled", "message": "Task cancelled by user"})
            return self.result
        except Exception as e:
            self.status = "failed"
            self.result = f"Agent error: {e}"
            self.logs.append({"step": "error", "message": str(e)})
            return self.result

    def cancel(self):
        """Signal the agent to stop at the next checkpoint."""
        self._cancel_event.set()

    def _check_cancelled(self):
        """Raise CancellationError if cancellation was requested."""
        if self._cancel_event.is_set():
            raise CancellationError("Task cancelled")

    async def run_async(self, task: str, progress_callback=None):
        """Run the agent asynchronously in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_with_progress, task, progress_callback)

    def _run_with_progress(self, task, progress_callback):
        """Wrapper that calls progress_callback after each round."""
        self.status = "running"
        self.logs = []
        self._cancel_event.clear()

        try:
            if not self.tool_registry:
                self.result = self.provider.generate(task)
                self.status = "completed"
                if progress_callback:
                    progress_callback(self.logs)
                return self.result

            result = self._run_with_tools(task, progress_callback)
            self.status = "completed"
            if progress_callback:
                progress_callback(self.logs)
            return result

        except CancellationError:
            self.status = "cancelled"
            self.logs.append({"step": "cancelled", "message": "Task cancelled by user"})
            if progress_callback:
                progress_callback(self.logs)
            raise
        except Exception as e:
            self.status = "failed"
            self.result = f"Agent error: {e}"
            self.logs.append({"step": "error", "message": str(e)})
            if progress_callback:
                progress_callback(self.logs)
            raise

    def _run_with_tools(self, task, progress_callback=None):
        """
        The multi-step tool-calling loop.

        The conversation looks like this to the LLM:

        [system]  You are an AI assistant with these tools...
        [user]    Analyze this project
        [assistant]  (tool_call: list_files)
        [tool]    main.py, agent/, providers/
        [assistant]  (tool_call: read_file main.py)
        [tool]    from fastapi import FastAPI ...
        [assistant]  Here is my analysis: ...    ← final answer
        """
        # Build the system prompt — tells the LLM what it can do
        system_prompt = self._build_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        tool_definitions = self.tool_registry.get_definitions()

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            # Check for cancellation at the start of each round
            self._check_cancelled()

            # Ask the LLM
            response = self.provider.chat(messages, tools=tool_definitions)

            # Check for cancellation after LLM response (before processing tool calls)
            self._check_cancelled()

            # Add the assistant's response to the conversation history
            messages.append(response)

            # Check if the LLM wants to call tools
            tool_calls = response.get("tool_calls")

            if not tool_calls:
                # No tool calls → this is the final answer
                self.result = response.get("content", "")
                self.logs.append({
                    "step": round_num,
                    "type": "final_answer",
                })
                if progress_callback:
                    progress_callback(self.logs)
                return self.result

            # Execute each tool the LLM requested
            for call in tool_calls:
                self._check_cancelled()

                func = call["function"]
                tool_name = func["name"]
                arguments = func.get("arguments", {})

                # Handle case where arguments arrive as a JSON string
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                self.logs.append({
                    "step": round_num,
                    "type": "tool_call",
                    "tool": tool_name,
                    "arguments": arguments,
                })

                # Run the tool through the registry (path validation happens there)
                tool_result = self.tool_registry.execute(tool_name, arguments)

                self.logs.append({
                    "step": round_num,
                    "type": "tool_result",
                    "tool": tool_name,
                    # Truncate in logs only — full result goes to the LLM
                    "result": tool_result[:500] if len(tool_result) > 500 else tool_result,
                })

                # Feed the tool result back into the conversation
                messages.append({"role": "tool", "content": tool_result})

            # Call progress callback after each round
            if progress_callback:
                progress_callback(self.logs)

        # Safety limit reached
        self.result = "Agent reached maximum tool rounds without a final answer."
        return self.result

    def _build_system_prompt(self):
        """
        Tell the LLM who it is and what directories it can access.
        Including the allowed paths helps the LLM use correct absolute paths
        in tool calls instead of guessing.
        """
        allowed = "\n".join(f"  - {d}" for d in self.tool_registry.allowed_dirs)

        return (
            "You are an AI assistant inside the AI Command Center.\n"
            "You have access to tools that let you inspect project files.\n\n"
            "ALLOWED DIRECTORIES (use absolute paths from this list):\n"
            f"{allowed}\n\n"
            "RULES:\n"
            "- Use tools when the task requires looking at real files or directories.\n"
            "- When you have enough information, provide your final answer directly.\n"
            "- Only use the tools provided. Do not invent tool names.\n"
            "- Use absolute paths from the allowed directories list above.\n"
        )