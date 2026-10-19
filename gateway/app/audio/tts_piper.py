"""Piper TTS provider with voice download and lazy loading."""

from __future__ import annotations
import asyncio
import logging
import sys
from app.audio.wav_utils import build_wav
import os
from pathlib import Path
from typing import Any

from app.audio.wav_utils import build_wav
from app.config import Settings
from app.schemas import TTSProvider

try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None  # type: ignore

logger = logging.getLogger(__name__)


class TTSPiper(TTSProvider):
    name = "piper"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._voice: PiperVoice | None = None

    def _voice_path(self) -> Path:
        if self.settings.tts_voice_path:
            return Path(self.settings.tts_voice_path)
        # Default: data_dir/voices/<voice>.onnx
        return self.settings.gateway_data_dir / "voices" / f"{self.settings.tts_voice}.onnx"

    async def ensure_voice(self) -> bool:
        """Download voice if missing (tolerate fail)."""
        voice_file = self._voice_path()
        if voice_file.exists():
            return True
        voice_name = self.settings.tts_voice
        dest_dir = voice_file.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "-m", "piper.download_voices",
            "--download-dir", str(dest_dir),
            voice_name,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode == 0:
                return voice_file.exists()
            logger.warning("voice download failed: %s", stderr.decode()[:300])
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice download error: %s", exc)
        return False

    def _lazy_voice(self) -> PiperVoice:
        if PiperVoice is None:
            raise RuntimeError("'piper-tts' package not installed")
        if self._voice is None:
            voice_file = self._voice_path()
            if not voice_file.exists():
                raise RuntimeError(f"Voice file missing: {voice_file}")
            self._voice = PiperVoice.load(str(voice_file))
        return self._voice

    async def synthesize(self, text: str, timeout_s: float = 15.0) -> bytes:
        """Synthesize text to WAV via to_thread with timeout."""
        try:
            voice = self._lazy_voice()
        except RuntimeError:
            # Voice file missing: try downloading once, then fail honestly.
            if not await self.ensure_voice():
                raise RuntimeError("piper voice not available (not downloaded)")
            self._voice = None
            voice = self._lazy_voice()

        def _synthesize_thread() -> bytes:
            chunks = bytearray()
            rate = 22050
            for chunk in voice.synthesize(text):
                chunks.extend(chunk.audio_int16_bytes)
                rate = chunk.sample_rate
            return build_wav(bytes(chunks), rate=rate)

        return await asyncio.wait_for(asyncio.to_thread(_synthesize_thread), timeout_s)

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Health check: voice file exists."""
        return self._voice_path().exists()