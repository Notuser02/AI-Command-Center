import os
from fastapi import FastAPI
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider
from agent.agent import Agent
from agent.tools import ToolRegistry

app = FastAPI()

ollama = OllamaProvider()
nebius = NebiusProvider()

# ── Tool security: the agent can ONLY access files inside this directory ──
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
tool_registry = ToolRegistry(allowed_dirs=[PROJECT_DIR])


@app.get("/status")
def status():
    return {"status": "AI Command Center is running"}


@app.get("/chat")
def chat(message: str, provider: str = "local"):

    if provider == "local":
        response = ollama.generate(message)

    elif provider == "online":
        response = nebius.generate(message)

    else:
        response = "Unknown provider. Use 'local' or 'online'."

    return {
        "provider": provider,
        "response": response
    }


@app.post("/agent/run")
def run_agent(task: str, provider: str = "local"):

    if provider == "local":
        selected_provider = ollama

    elif provider == "online":
        selected_provider = nebius

    else:
        return {"error": "Unknown provider. Use 'local' or 'online'."}

    agent = Agent(selected_provider, tool_registry=tool_registry)

    result = agent.run(task)

    return {
        "provider": provider,
        "status": agent.status,
        "result": result,
        "logs": agent.logs
    }