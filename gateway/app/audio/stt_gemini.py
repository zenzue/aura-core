"""Gemini STT provider with lazy import and error handling."""

import asyncio
import os
from typing import Any

from app.config import Settings
from app.schemas import STTProvider

try:
    import google.genai as genai
except ImportError:
    genai = None  # type: ignore


class STTGemini(STTProvider):
    name = "gemini"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: genai.Client | None = None

    def _lazy_client(self) -> genai.Client:
        if genai is None:
            raise RuntimeError("'google-genai' package not installed")
        if self._client is None:
            api_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not set")
            self._client = genai.Client(api_key=api_key)
        return self._client

    async def transcribe(self, wav: bytes, timeout_s: float = 20.0) -> str:
        """Transcribe WAV via Gemini audio model."""
        client = self._lazy_client()

        model = self.settings.gemini_model or "gemini-2.5-flash"
        prompt = "Transcribe verbatim."

        part = genai.types.Part.from_bytes(data=wav, mime_type="audio/wav")

        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[prompt, part],
                ),
                timeout=timeout_s,
            )
            try:
                text = resp.text or ""
            except Exception:  # noqa: BLE001
                text = resp.candidates[0].content.parts[0].text or ""
            return text.strip()
        except Exception as e:
            # Clean error: never raise, return error dict?
            # Per contract: transcribe returns str; so we return placeholder
            # and log externally. In gateway, this becomes "STT error".
            return ""

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Health check: package installed and API key present."""
        return genai is not None and bool(self.settings.gemini_api_key)
