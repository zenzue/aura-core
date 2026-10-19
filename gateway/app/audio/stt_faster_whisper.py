"""Faster-Whisper STT provider with lazy import and VAD filter."""

import asyncio
from typing import Any

from app.config import Settings
from app.schemas import STTProvider

try:
    from faster_whisper import WhisperModel
    from faster_whisper.utils import get_assets_path
    import numpy as np
except ImportError:
    WhisperModel = None  # type: ignore


class STTFasterWhisper(STTProvider):
    name = "faster_whisper"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: WhisperModel | None = None

    def _lazy_load(self) -> WhisperModel:
        if WhisperModel is None:
            raise RuntimeError("'faster-whisper' package not installed")
        if self._model is None:
            self._model = WhisperModel(
                self.settings.stt_model_size,
                device="cpu",
                compute_type="int8",
                # Optional: download assets on first use?
                # local_files_only=True,  # fail rather than download
            )
        return self._model

    async def transcribe(self, wav: bytes, timeout_s: float = 20.0) -> str:
        """Transcribe 16kHz mono PCM16 WAV to text."""
        model = self._lazy_load()

        # VAD filter: split on silence (using beam search VAD)
        # Faster-whisper already includes VAD, but we explicitly enable
        segments, _ = await asyncio.to_thread(
            model.transcribe,
            wav,
            beam_size=1,
            best_of=5,
            patience=1.0,
            length_penalty=1.0,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            condition_on_previous_text=False,
            initial_prompt=None,
            prefix_images=None,
            suppress_blank=True,
            suppress_punctuation=False,
            suppress_special_tokens=False,
            word_timestamps=False,
            vad_filter=True,  # <--- explicit
            vad_parameters=dict(threshold=0.5, window_size=3, min_speech_duration=0.1),
        )

        text = " ".join(segment.text.strip() for segment in segments)
        return text

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Health check: try loading model."""
        try:
            self._lazy_load()
            return True
        except Exception:
            return False