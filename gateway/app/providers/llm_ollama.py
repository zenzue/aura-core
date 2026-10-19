import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.providers.llm_base import LLMProvider, ReplyParseError

logger = logging.getLogger(__name__)


class OllamaLLMProvider(LLMProvider):
    """Ollama LLM provider."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.ollama_base_url or "http://localhost:11434"
        self.model = settings.ollama_model or "llama3.1"
        self.timeout = settings.llm_timeout_s

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate reply using Ollama."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Convert messages to Ollama format
            ollama_messages = []
            for msg in messages:
                role = "user" if msg.get("role") == "user" else "assistant"
                ollama_messages.append({"role": role, "content": msg.get("content", "")})

            # Add system prompt if provided
            if system_prompt:
                ollama_messages.insert(0, {"role": "system", "content": system_prompt})

            # Build request
            request_data = {
                "model": self.model,
                "messages": ollama_messages,
                "format": "json",
                "options": {
                    "temperature": self.settings.ollama_temperature or 0.8,
                    "top_p": self.settings.ollama_top_p or 0.9,
                },
            }

            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=request_data,
                )
                response.raise_for_status()

                # Parse response
                data = response.json()
                if "message" in data and "content" in data["message"]:
                    raw_reply = data["message"]["content"]
                    return self.parse_llm_reply(raw_reply)
                else:
                    raise ValueError("Unexpected response format from Ollama")

            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Ollama generate error: {e}")
                raise

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Check Ollama provider health."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/version")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False