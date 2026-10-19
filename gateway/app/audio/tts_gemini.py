"""Gemini TTS provider with format conversion notes."""

import asyncio
import os
from typing import Any

from app.config import Settings
from app.schemas import TTSProvider

try:
    import google.genai as genai
except ImportError:
    genai = None  # type: ignore


class TTSGemini(TTSProvider):
    name = "gemini_tts"

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

    async def synthesize(self, text: str, timeout_s: float = 15.0) -> bytes:
        """
        Synthesize text via Gemini TTS.
        Returns: WAV bytes (24kHz mono PCM16) via build_wav(24kHz).
        Documented mime handling: audio/l16 (16kHz?) but actual is 24kHz PCM16.
        """
        client = self._lazy_client()

        model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
        voice_config = genai.types.SpeechConfig(
            voice=os.getenv("GEMINI_TTS_VOICE", "Puck"),
            speaking_rate=1.0,
        )

        try:
            resp = await asyncio.wait_for(
                client.aio.generate_content(
                    model=model,
                    contents=[text],
                    config=voice_config,
                ),
                timeout=timeout_s,
            )
            # resp has parts[0].inline_data.data (bytes) and mime_type
            if not resp.parts or not hasattr(resp.parts[0], "inline_data"):
                return b""
            data = resp.parts[0].inline_data.data  # type: ignore
            if not data:
                return b""

            # Documented format: expect audio/l16 but observed 24kHz PCM16
            # We'll treat as raw PCM16 @ 24kHz and wrap in WAV
            from app.audio.wav_utils import build_wav

            wav_bytes = build_wav(data, 24000)
            return wav_bytes

        except Exception as e:
            # Never raise; gateway catches and returns error
            return b""

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Health check: try generate_content."""
        try:
            client = self._lazy_client()
            await asyncio.wait_for(
                client.aio.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=["test"],
                    config=genai.types.SpeechConfig(voice="Puck"),
                ),
                timeout=timeout_s,
            )
            return True
        except Exception:
            return False