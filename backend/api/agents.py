"""
Agent routes.

The /agent/run endpoint is the original "fire and forget" agent call.
It runs synchronously — the request blocks until the agent finishes.

For background execution with status tracking, use the /tasks endpoints instead.
"""

from fastapi import APIRouter
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider
from agent.agent import Agent
from agent.tools import ToolRegistry

router = APIRouter()

ollama = OllamaProvider()
nebius = NebiusProvider()

# Will be set by main.py when mounting this router
tool_registry: ToolRegistry = None


def init(registry: ToolRegistry):
    """Called by main.py to inject the tool registry."""
    global tool_registry
    tool_registry = registry


@router.post("/agent/run")
def run_agent(task: str, provider: str = "local", model: str = "qwen3.5:9b"):

    if provider == "local":
        selected_provider = OllamaProvider(model=model)

    elif provider == "online":
        selected_provider = nebius

    else:
        return {"error": "Unknown provider. Use 'local' or 'online'."}

    agent = Agent(selected_provider, tool_registry=tool_registry)

    result = agent.run(task)

    return {
        "provider": provider,
        "model": model,
        "status": agent.status,
        "result": result,
        "logs": agent.logs
    }
