"""Gemini LLM provider (google-genai SDK)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

try:
    import google.genai as genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None


class GeminiLLMProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._client = None
        self.model = settings.gemini_model or "gemini-2.0-flash"
        self.api_key = settings.gemini_api_key

    def _get_client(self):
        if genai is None:
            raise RuntimeError("'google-genai' package not installed")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()

        contents = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": str(msg.get("content", ""))}]})

        config_kwargs: Dict[str, Any] = {
            "temperature": self.settings.gemini_temperature,
            "top_p": self.settings.gemini_top_p,
            "candidate_count": 1,
            "response_mime_type": "application/json",
        }
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if tools:
            declarations = []
            for tool in tools:
                declarations.append(genai_types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters"),
                ))
            config_kwargs["tools"] = [genai_types.Tool(function_declarations=declarations)]

        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            ),
            timeout=self.settings.llm_timeout_s,
        )

        text = ""
        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001
            try:
                cand = resp.candidates[0].content.parts[0].text
                text = cand or ""
            except Exception:  # noqa: BLE001
                text = ""
        if not text.strip():
            raise ValueError("Gemini returned an empty reply")
        return self.parse_llm_reply(text)

    async def health(self, timeout_s: float = 5.0) -> bool:
        return genai is not None and bool(self.api_key)
