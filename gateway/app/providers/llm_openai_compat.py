import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.providers.llm_base import LLMProvider, ReplyParseError

logger = logging.getLogger(__name__)


class OpenAICompatLLMProvider(LLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.openai_base_url or "https://api.openai.com/v1"
        self.model = settings.openai_model or "gpt-3.5-turbo"
        self.api_key = settings.openai_api_key
        self.timeout = settings.llm_timeout or 30.0

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate reply using OpenAI-compatible API."""
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Convert messages to OpenAI format
            openai_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                openai_messages.append({"role": role, "content": content})

            # Add system prompt if provided
            if system_prompt:
                openai_messages.insert(0, {"role": "system", "content": system_prompt})

            # Build request
            request_data = {
                "model": self.model,
                "messages": openai_messages,
                "response_format": {"type": "json_object"},
                "temperature": self.settings.openai_temperature or 0.7,
                "max_tokens": 1000,
            }

            # Add tools if provided
            if tools:
                request_data["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        },
                    }
                    for tool in tools
                ]

            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=request_data,
                )
                response.raise_for_status()

                # Parse response
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        raw_reply = choice["message"]["content"]
                        return self.parse_llm_reply(raw_reply)
                    else:
                        raise ValueError("Unexpected response format from OpenAI")
                else:
                    raise ValueError("No choices in OpenAI response")

            except httpx.HTTPStatusError as e:
                logger.error(f"OpenAI HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"OpenAI generate error: {e}")
                raise

    async def health(self) -> bool:
        """Check OpenAI provider health."""
        if not self.api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False