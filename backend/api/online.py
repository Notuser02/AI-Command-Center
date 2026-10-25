"""
Online provider configuration — "bring your own API key".

Endpoints:
  GET  /online/config   → {base_url, api_key_set, default_model}  (never the key)
  POST /online/config   → partial update {base_url?, api_key?, default_model?};
                          empty/missing api_key keeps the existing one.
                          Validates by listing models from the service.
  GET  /online/models   → live model list from the configured service
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import SettingsRepository
from providers.online import OnlineProvider

router = APIRouter(prefix="/online", tags=["online"])

repo = SettingsRepository()

KEY_BASE = "online_base_url"
KEY_API = "online_api_key"
KEY_MODEL = "online_default_model"


class OnlineConfigIn(BaseModel):
    base_url: str = ""
    api_key: str = ""          # empty = keep existing
    default_model: str = ""    # empty = keep existing


def _load_provider() -> OnlineProvider:
    env_fallback = ""
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        env_fallback = os.getenv("ONLINE_API_KEY") or os.getenv("NEBIUS_API_KEY") or ""
    except Exception:
        pass
    return OnlineProvider(
        base_url=repo.get(KEY_BASE) or "",
        api_key=repo.get(KEY_API) or env_fallback,
        model=repo.get(KEY_MODEL) or "",
    )


@router.get("/config")
def get_config():
    provider = _load_provider()
    return {
        "base_url": provider.base_url,
        "api_key_set": bool(provider.api_key),
        "default_model": provider.model,
    }


@router.post("/config")
def save_config(config_in: OnlineConfigIn):
    current = _load_provider()

    # Candidate = new values on top of existing ones (empty key/base = keep current)
    base_url = (config_in.base_url or "").strip().rstrip("/") or current.base_url
    api_key = (config_in.api_key or "").strip() or current.api_key
    default_model = (config_in.default_model or "").strip() or current.model

    candidate = OnlineProvider(base_url=base_url, api_key=api_key, model=default_model)

    # Validate BEFORE persisting: a typo'd URL or bad key must never
    # overwrite a working configuration.
    models = []
    if candidate.base_url and candidate.api_key:
        try:
            models = candidate.list_models()
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # Validation passed (or config still incomplete) — safe to persist
    if (config_in.base_url or "").strip():
        repo.set(KEY_BASE, base_url)
    if (config_in.api_key or "").strip():
        repo.set(KEY_API, api_key)
    if default_model:
        repo.set(KEY_MODEL, default_model)

    if models:
        return {
            "ok": True,
            "base_url": base_url,
            "api_key_set": True,
            "default_model": default_model,
            "models": models[:100],
        }
    return get_config()


@router.get("/models")
def list_online_models():
    provider = _load_provider()
    if not provider.is_configured():
        return {"models": [], "error": "Online provider not configured"}
    try:
        return {"models": provider.list_models()[:100], "error": None}
    except RuntimeError as e:
        return {"models": [], "error": str(e)}
