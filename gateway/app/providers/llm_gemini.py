import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from google.genai import ClientV1beta1AsyncClient as Client
from google.genai.types import (
    GenerateContentConfig,
    Tool as GenAITool,
    ToolConfig,
)

from app.config import Settings
from app.providers.llm_base import LLMProvider, ReplyParseError

logger = logging.getLogger(__name__)


class GeminiLLMProvider(LLMProvider):
    """Google Generative AI LLM provider."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.client: Optional[Client] = None
        self.model = settings.gemini_model or "gemini-2.0-flash"
        self.api_key = settings.gemini_api_key

    async def _get_client(self) -> Client:
        """Get or create async client."""
        if self.client is None:
            self.client = Client(
                api_key=self.api_key,
                httpx_client=httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0),
                ),
            )
        return self.client

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate reply using Google Generative AI."""
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        client = await self._get_client()

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "assistant"
            gemini_messages.append(
                {"role": role, "parts": [{"text": msg.get("content", "")}]}
            )

        # Build tool specs for Gemini
        gemini_tools: Optional[List[GenAITool]] = None
        if tools:
            gemini_tools = []
            for tool in tools:
                gemini_tools.append(
                    GenAITool(
                        function_declarations=[
                            {
                                "name": tool["name"],
                                "description": tool.get("description", ""),
                                "parameters": tool.get("parameters", {}),
                                "strict": False,
                            }
                        ]
                    )
                )

        # Generate content
        try:
            response = await client.aio.generate_content(
                model=self.model,
                contents=gemini_messages,
                tools=gemini_tools,
                generation_config=GenerateContentConfig(
                    temperature=self.settings.gemini_temperature or 0.7,
                    top_p=self.settings.gemini_top_p or 0.9,
                    candidate_count=1,
                ),
                safety_settings=[],  # Use default safety settings
            )

            # Parse response
            if response.candidates and response.candidates[0].content:
                raw_reply = response.candidates[0].content.parts[0].text
                return self.parse_llm_reply(raw_reply)
            else:
                raise ValueError("No response from Gemini")

        except Exception as e:
            logger.error(f"Gemini generate error: {e}")
            raise

    async def health(self) -> bool:
        """Check Gemini provider health."""
        if not self.api_key:
            return False

        try:
            client = await self._get_client()
            # Simple health check - list models
            await client.aio.list_models()
            return True
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return False