"""Piper TTS provider with voice download and lazy loading."""

import asyncio
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

        # Attempt download (uv run python -m piper.download_voices <voice>)
        voice_name = self.settings.tts_voice
        cmd = ["uv", "run", "python", "-m", "piper.download_voices", voice_name]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                # Download puts into current dir? or voices/ ?
                # Piper download_voices writes to current working dir.
                # We expect <voice_name>.onnx there; move it.
                downloaded = Path.cwd() / f"{voice_name}.onnx"
                if downloaded.exists():
                    downloaded.rename(voice_file)
                    return True
            # Tolerate fail: return False
        except Exception:
            pass  # tolerate
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