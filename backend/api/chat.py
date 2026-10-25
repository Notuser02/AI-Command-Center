"""
Chat & status routes.

These are the simplest endpoints — no database, no background tasks.
/status is a health check, /chat is direct LLM interaction.
"""

from fastapi import APIRouter
from providers.ollama import OllamaProvider
from providers.nebius import NebiusProvider

import requests as _http

router = APIRouter()

ollama = OllamaProvider()
nebius = NebiusProvider()

# tools-capability per model, cached for the server's lifetime
# (a model's capabilities don't change while it's installed)
_tools_cache = {}


def _model_supports_tools(model: str) -> bool:
    """Ask Ollama's /api/show for the model's capabilities ('tools' flag),
    cached per model. New models are handled automatically — no lists here."""
    if model in _tools_cache:
        return _tools_cache[model]
    supports = False
    try:
        resp = _http.post(
            f"{ollama.base_url}/api/show",
            json={"model": model},
            timeout=10,
        )
        if resp.status_code == 200:
            caps = resp.json().get("capabilities") or []
            supports = "tools" in caps
    except Exception:
        supports = True  # can't tell — assume yes rather than scare users off
    _tools_cache[model] = supports
    return supports


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


@router.get("/models/detail")
def list_models_detail():
    """Rich model info: which local models support tool calling.
    Labels come from Ollama itself, so models pulled later are covered."""
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
        "local": [{"name": m, "tools": _model_supports_tools(m)} for m in local_models],
        "online": [{"name": m, "tools": True} for m in online_models],
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
