"""LLM provider factory."""
import logging
from typing import Optional

from app.config import Settings
from app.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)


def build_llm(settings: Settings) -> Optional[LLMProvider]:
    provider = (settings.ai_provider or "ollama").strip().lower()
    if provider == "gemini":
        from app.providers.llm_gemini import GeminiLLMProvider
        return GeminiLLMProvider(settings)
    if provider == "ollama":
        from app.providers.llm_ollama import OllamaLLMProvider
        return OllamaLLMProvider(settings)
    if provider == "openai_compat":
        from app.providers.llm_openai_compat import OpenAICompatLLMProvider
        return OpenAICompatLLMProvider(settings)
    raise ValueError(f"Unknown AI provider: {provider}")
