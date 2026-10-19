import logging
from typing import Any, Dict, Optional

from app.config import Settings
from app.providers.llm_base import LLMProvider, ReplyParseError

logger = logging.getLogger(__name__)


def build_llm(settings: Settings) -> Optional[LLMProvider]:
    """Build LLM provider based on settings."""
    provider_name = settings.ai_provider or "ollama"
    
    try:
        if provider_name == "gemini":
            from app.providers.llm_gemini import GeminiLLMProvider
            return GeminiLLMProvider(settings)
        elif provider_name == "ollama":
            from app.providers.llm_ollama import OllamaLLMProvider
            return OllamaLLMProvider(settings)
        elif provider_name == "openai_compat":
            from app.providers.llm_openai_compat import OpenAICompatLLMProvider
            return OpenAICompatLLMProvider(settings)
        else:
            raise ValueError(f"Unknown AI provider: {provider_name}")
    except Exception as e:
        logger.error(f"Failed to build LLM provider {provider_name}: {e}")
        return None