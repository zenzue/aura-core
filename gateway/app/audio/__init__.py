"""Audio providers (STT/TTS) with lazy imports."""

from app.schemas import STTProvider, TTSProvider
from .wav_utils import parse_wav, build_wav, rms
from .stt_faster_whisper import STTFasterWhisper
from .stt_gemini import STTGemini
from .tts_piper import TTSPiper
from .tts_gemini import TTSGemini

__all__ = [
    "build_stt",
    "build_tts",
    "parse_wav",
    "build_wav",
    "rms",
]


def build_stt(settings) -> STTProvider | None:
    """Factory: returns STT provider or None (missing package)."""
    provider = settings.stt_provider
    if provider == "faster_whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return None
        return STTFasterWhisper(settings)
    elif provider == "gemini":
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return None
        return STTGemini(settings)
    elif provider:
        raise ValueError(f"Unknown STT provider: {provider}")
    return None


def build_tts(settings) -> TTSProvider | None:
    """Factory: returns TTS provider or None (missing package)."""
    provider = settings.tts_provider
    if provider == "piper":
        try:
            import piper  # noqa: F401
        except ImportError:
            return None
        return TTSPiper(settings)
    elif provider == "gemini_tts":
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return None
        return TTSGemini(settings)
    elif provider:
        raise ValueError(f"Unknown TTS provider: {provider}")
    return None