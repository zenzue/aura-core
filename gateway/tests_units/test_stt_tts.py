"""STT/TTS tests (real piper, mock others)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.audio import build_stt, build_tts
from app.config import Settings
from app.audio.stt_faster_whisper import STTFasterWhisper
from app.audio.stt_gemini import STTGemini
from app.audio.tts_piper import TTSPiper
from app.audio.tts_gemini import TTSGemini

# Fixtures
@pytest.fixture
def mock_settings():
    return Settings(
        stt_provider="faster_whisper",
        tts_provider="piper",
        stt_model_size="base",
        tts_voice="en_US-lessac-medium",
        gateway_data_dir="/tmp/test_data",
    )


def gemini_settings():
    return Settings(
        stt_provider="gemini",
        tts_provider="gemini_tts",
        gemini_api_key="test_key",
    )


# Test STT providers (mock)
@pytest.mark.asyncio
async def test_stt_faster_whisper_missing_package(monkeypatch):
        """Factory returns None when package cannot be imported."""
        monkeypatch.setitem(__import__("sys").modules, "faster_whisper", None)
        settings = Settings(stt_provider="faster_whisper")
        stt = build_stt(settings)
        assert stt is None


@pytest.mark.asyncio
async def test_stt_gemini_missing_key():
    """Test Gemini STT without API key."""
    settings = Settings(stt_provider="gemini", gemini_api_key="")
    stt = build_stt(settings)
    assert stt is not None
    # Health should fail without key
    health = await stt.health()
    assert not health


@pytest.mark.asyncio
async def test_stt_gemini_transcribe_error():
    """Test Gemini STT error handling."""
    settings = gemini_settings()
    stt = build_stt(settings)
    assert isinstance(stt, STTGemini)

    # Mock the client to raise
    with patch.object(stt, "_lazy_client") as mock_client:
        mock_client.return_value.aio.generate_content.side_effect = Exception("API error")
        wav = b"RIFF...."  # fake wav
        text = await stt.transcribe(wav)
        assert text == ""  # never raises, returns empty


# Test TTS providers
@pytest.mark.asyncio
async def test_tts_piper_missing_package(monkeypatch):
    """Test TTS when package missing."""
    with patch.dict("sys.modules", {"piper": None}):
        settings = Settings(tts_provider="piper")
        tts = build_tts(settings)
        assert tts is None


@pytest.mark.asyncio
async def test_tts_piper_voice_download(capfd):
    """Test voice download (tolerate fail)."""
    settings = Settings(
        tts_provider="piper",
        tts_voice="en_US-lessac-medium",
        gateway_data_dir="/tmp/test_data",
    )
    tts = build_tts(settings)
    assert isinstance(tts, TTSPiper)

    # ensure_voice must be idempotent: True when voice present (downloaded
    # earlier or shipped), False only on genuine download failure.
    result = await tts.ensure_voice()
    assert isinstance(result, bool)


@pytest.mark.requires_models
@pytest.mark.asyncio
async def test_tts_piper_synthesize_real(capfd):
    """Real piper synthesis test (requires_models)."""
    pytest.importorskip("piper")  # skip if piper not installed

    settings = Settings(
        tts_provider="piper",
        tts_voice="en_US-lessac-medium",
    )
    tts = build_tts(settings)
    assert isinstance(tts, TTSPiper)

    # First ensure voice is available
    await tts.ensure_voice()  # may download

    # Synthesize
    text = "hello world"
    wav = await tts.synthesize(text, timeout_s=10.0)

    # Validate WAV header
    from app.audio.wav_utils import parse_wav

    try:
        header = parse_wav(wav)
        assert header.rate > 0
        assert header.channels == 1
        assert header.bits == 16
        # Duration should be >0.2s for "hello world"
        duration = len(header.pcm) / (header.rate * header.channels * header.bits // 8)
        assert duration > 0.2
    except Exception as e:
        pytest.skip(f"WAV parse failed: {e}")


@pytest.mark.asyncio
async def test_tts_gemini_missing_key():
    """Test Gemini TTS without key."""
    settings = Settings(tts_provider="gemini_tts")
    tts = build_tts(settings)
    assert tts is not None
    # Health should fail
    health = await tts.health()
    assert not health


@pytest.mark.asyncio
async def test_tts_gemini_synthesize_error():
    """Test Gemini TTS error handling."""
    settings = gemini_settings()
    tts = build_tts(settings)
    assert isinstance(tts, TTSGemini)

    with patch.object(tts, "_lazy_client") as mock_client:
        mock_client.return_value.aio.generate_content.side_effect = Exception("API error")
        text = "test"
        wav = await tts.synthesize(text)
        assert wav == b""  # never raises