"""WAV utilities tests."""

import pytest

from app.audio.wav_utils import parse_wav, build_wav, rms


def test_parse_wav_valid():
    """Test parsing valid WAV header."""
    # Minimal valid WAV: RIFF + fmt + data
    wav_bytes = (
        # RIFF header
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVE"
        # fmt chunk
        + b"fmt "
        + (16).to_bytes(4, "little")
        + b"\x01\x00"  # format PCM
        + b"\x01\x00"  # channels=1
        + (16000).to_bytes(4, "little")  # sample rate
        + (32000).to_bytes(4, "little")  # byte rate
        + b"\x02\x00"  # block align
        + b"\x10\x00"  # bits per sample
        # data chunk
        + b"data"
        + (8).to_bytes(4, "little")
        + b"\x00\x01\x02\x03\x04\x05\x06\x07"  # 4 samples @16-bit
    )

    header = parse_wav(wav_bytes)
    assert header.rate == 16000
    assert header.channels == 1
    assert header.bits == 16
    assert header.pcm == b"\x00\x01\x02\x03\x04\x05\x06\x07"


def test_parse_wav_invalid_too_short():
    """Test parsing invalid short WAV."""
    with pytest.raises(ValueError, match="WAV too short"):
        parse_wav(b"RIFF....")  # incomplete


def test_parse_wav_not_mono():
    """Test parsing stereo WAV with require_mono=True."""
    wav_bytes = (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + b"\x01\x00"  # format PCM
        + b"\x02\x00"  # channels=2 (stereo)
        + (16000).to_bytes(4, "little")
        + (64000).to_bytes(4, "little")
        + b"\x04\x00"  # block align
        + b"\x10\x00"  # bits per sample
        + b"data"
        + (8).to_bytes(4, "little")
        + b"\x00\x01\x02\x03"  # 2 samples stereo
    )

    with pytest.raises(ValueError, match="Only mono audio supported"):
        parse_wav(wav_bytes)


def test_build_wav_roundtrip():
    """Test build_wav + parse_wav roundtrip."""
    pcm = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    wav = build_wav(pcm, 16000)
    header = parse_wav(wav)
    assert header.rate == 16000
    assert header.pcm == pcm


def test_rms_amplitude():
    """Test RMS calculation."""
    # Full scale alternating
    pcm = b"\x7f\xff" + b"\x80\x00" + b"\x7f\xff" + b"\x80\x00"
    # Samples: 32767, -32768, 32767, -32768
    # Mean squares: (32767² + (-32768)² + ...) / 4 ≈ (1.07e9 + 1.07e9 + ...) / 4 ≈ 1.07e9
    # RMS ≈ sqrt(1.07e9) ≈ 32767
    assert rms(pcm) == 32767

    # Zero
    assert rms(b"\x00\x00" * 10) == 0