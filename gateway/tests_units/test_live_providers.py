"""LIVE integration tests: only run against genuinely reachable endpoints.

Set the env vars below (plus models) when real services exist:
  AURA_LIVE_OLLAMA_URL=http://host:11434  AURA_LIVE_OLLAMA_MODEL=qwen2.5:7b
  AURA_LIVE_LLAMACPP_URL=http://host:8080/v1  AURA_LIVE_LLAMACPP_MODEL=...
  AURA_LIVE_GEMINI_KEY + AURA_LIVE_GEMINI_MODEL (optional)
A missing endpoint skips the test; nothing is ever faked.
"""
from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.providers import build_llm


def _skip_or_settings(url_env: str, model_env: str, **extra) -> Settings:
    url = os.getenv(url_env, "").strip()
    model = os.getenv(model_env, "").strip()
    if not url or not model:
        pytest.skip(f"{url_env}/{model_env} not configured - live service absent")
    fields = dict(extra)
    fields.update({
        "ollama_base_url": url, "ollama_model": model,
    } if "OLLAMA" in url_env else {
        "llamacpp_base_url": url, "llamacpp_model": model,
    })
    return Settings(**fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_ollama_roundtrip() -> None:
    settings = _skip_or_settings("AURA_LIVE_OLLAMA_URL", "AURA_LIVE_OLLAMA_MODEL",
                                 ai_provider="ollama")
    prov = build_llm(settings)
    assert prov is not None
    assert await prov.health(timeout_s=10.0) is True
    models = await prov.list_models()
    assert settings.ollama_model in models


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_llamacpp_roundtrip() -> None:
    settings = _skip_or_settings("AURA_LIVE_LLAMACPP_URL", "AURA_LIVE_LLAMACPP_MODEL",
                                 ai_provider="llamacpp")
    prov = build_llm(settings)
    assert prov is not None
    assert await prov.health(timeout_s=10.0) is True
    models = await prov.list_models()
    assert settings.llamacpp_model in models


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_gemini_roundtrip() -> None:
    key = os.getenv("AURA_LIVE_GEMINI_KEY", "").strip()
    model = os.getenv("AURA_LIVE_GEMINI_MODEL", "").strip()
    if not key or not model:
        pytest.skip("AURA_LIVE_GEMINI_KEY/MODEL not configured")
    settings = Settings(ai_provider="gemini", gemini_api_key=key, gemini_model=model)
    prov = build_llm(settings)
    assert prov is not None
    assert await prov.health(timeout_s=15.0) is True
