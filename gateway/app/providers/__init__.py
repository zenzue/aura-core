"""LLM provider factory (Gemini | Ollama | llama.cpp)."""
from __future__ import annotations

import logging
from typing import Optional

from app.config import Settings
from app.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)


def build_llm(settings: Settings, provider: Optional[str] = None) -> Optional[LLMProvider]:
    """Build a provider instance for `provider` (default: active selection).

    Returns None when the selection is incomplete (missing key/model/URL) so
    the gateway can keep answering with honest errors; raises ValueError only
    for an unknown provider name.
    """
    name = (provider or settings.ai_provider or "").strip().lower()
    if not name or name not in ("gemini", "ollama", "llamacpp"):
        raise ValueError(f"Unknown AI provider: {name!r}")
    if provider is None:
        problems = settings.problems()
        if problems:
            for p in problems:
                logger.warning("llm provider disabled: %s", p)
            return None
    if name == "gemini":
        from app.providers.llm_gemini import GeminiLLMProvider
        return GeminiLLMProvider(settings)
    if name == "ollama":
        from app.providers.llm_ollama import OllamaLLMProvider
        return OllamaLLMProvider(settings)
    from app.providers.llm_llamacpp import LlamaCppLLMProvider
    return LlamaCppLLMProvider(settings)
