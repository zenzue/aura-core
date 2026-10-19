"""Faster-Whisper STT provider with lazy import and VAD filter."""

import asyncio
import io
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
        """Transcribe 16kHz mono s16 WAV bytes to text."""
        model = self._lazy_load()

        # Decode WAV ourselves: faster-whisper's av-based decode_audio is
        # broken with PyAV>=19 on this platform; passing a float32 ndarray
        # skips that path entirely.
        from app.audio.wav_utils import parse_wav

        header = parse_wav(wav, require_mono=True)
        samples = np.frombuffer(header.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if header.rate != 16000:
            dur = samples.shape[0] / header.rate
            target = int(dur * 16000)
            src_idx = np.linspace(0.0, samples.shape[0] - 1.0, target, dtype=np.float64)
            base = np.floor(src_idx).astype(np.int64)
            nxt = np.minimum(base + 1, samples.shape[0] - 1)
            frac = (src_idx - base).astype(np.float32)
            samples = samples[base] * (1.0 - frac) + samples[nxt] * frac

        segments, _info = await asyncio.wait_for(
            asyncio.to_thread(
                model.transcribe,
                samples,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400.0),
                word_timestamps=False,
            ),
            timeout_s,
        )

        text = " ".join(segment.text.strip() for segment in segments)
        return text

    async def health(self, timeout_s: float = 5.0) -> bool:
        """Health check: package importable. Model loads (may download) on
        first transcribe; health must not trigger a big download."""
        return WhisperModel is not None