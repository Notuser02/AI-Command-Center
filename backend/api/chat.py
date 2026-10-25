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


@router.get("/models")
def list_models():
    """Return all available models: local (Ollama, live) and online
    (live from the configured OpenAI-compatible service, else empty)."""
    local_models = OllamaProvider.list_models()
    online_models = []
    try:
        from api.online import _load_provider
        provider = _load_provider()
        if provider.is_configured():
            online_models = provider.list_models()[:100]
    except Exception:
        online_models = []
    return {
        "local": local_models,
        "online": online_models,
        "default": {
            "local": "qwen3.5:9b",
            "online": online_models[0] if online_models else ""
        }
    }


@router.get("/chat")
def chat(message: str, provider: str = "local", model: str = "qwen3.5:9b"):

    if provider == "local":
        provider_instance = OllamaProvider(model=model)
        response = provider_instance.generate(message)

    elif provider == "online":
        response = nebius.generate(message)

    else:
        response = "Unknown provider. Use 'local' or 'online'."

    return {
        "provider": provider,
        "model": model,
        "response": response
    }
