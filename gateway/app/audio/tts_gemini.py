"""Gemini TTS provider (google-genai SDK, response_modalities AUDIO)."""
from __future__ import annotations

import asyncio
import logging
import os

from app.audio.wav_utils import build_wav
from app.config import Settings
from app.schemas import TTSProvider

logger = logging.getLogger(__name__)

try:
    import google.genai as genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"


class TTSGemini(TTSProvider):
    name = "gemini_tts"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _lazy_client(self):
        if genai is None:
            raise RuntimeError("'google-genai' package not installed")
        api_key = self.settings.resolved_gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        if self._client is None:
            self._client = genai.Client(api_key=api_key)
        return self._client

    async def synthesize(self, text: str, timeout_s: float = 15.0) -> bytes:
        """Synthesize speech; returns mono PCM16 WAV at 24 kHz."""
        if not text or not text.strip():
            return b""
        client = self._lazy_client()
        voice = os.getenv("GEMINI_TTS_VOICE") or "Puck"
        try:
            config = genai_types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        ),
                    ),
                ),
            )
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=os.getenv("GEMINI_TTS_MODEL", DEFAULT_MODEL),
                    contents=[text],
                    config=config,
                ),
                timeout=timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gemini tts: request failed: %s", exc)
            return b""
        try:
            part = resp.candidates[0].content.parts[0]
            inline = part.inline_data
            if inline is None or not inline.data:
                return b""
            # Gemini TTS audio is linear PCM 16-bit mono 24kHz
            return build_wav(bytes(inline.data), rate=24000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gemini tts: no inline audio in response: %s", exc)
            return b""

    async def health(self, timeout_s: float = 5.0) -> bool:
        return genai is not None and bool(self.settings.resolved_gemini_api_key)
