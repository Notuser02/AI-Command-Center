"""
Chat & status routes.

These are the simplest endpoints — no database, no background tasks.
/status is a health check, /chat is direct LLM interaction.
"""

from fastapi import APIRouter
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider

router = APIRouter()

ollama = OllamaProvider()
nebius = NebiusProvider()


@router.get("/status")
def status():
    return {"status": "AI Command Center is running"}


@router.get("/chat")
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
