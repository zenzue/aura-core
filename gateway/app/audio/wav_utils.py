"""WAV file utilities with strict header validation."""

import struct
from typing import NamedTuple


class WavHeader(NamedTuple):
    pcm: bytes
    rate: int
    channels: int
    bits: int


def parse_wav(wav_bytes: bytes, require_mono: bool = True) -> WavHeader:
    """
    Strict RIFF/WAV header parser.
    Expected: PCM16, mono (if require_mono=True), little-endian.
    Returns only the PCM data + metadata.
    """
    if len(wav_bytes) < 44:
        raise ValueError("WAV too short (<44 bytes)")

    # RIFF header
    riff, riff_size, wave = struct.unpack("<4sI4s", wav_bytes[:12])
    if riff != b"RIFF" or wave != b"WAVE":
        raise ValueError("Invalid RIFF/WAVE header")

    # fmt chunk (must be before data)
    fmt_id, fmt_size, fmt_code, channels, rate, avg_bps, block_align, bits = struct.unpack(
        "<4sIHHIIHH", wav_bytes[12:36]
    )
    if fmt_id != b"fmt ":
        raise ValueError("Missing 'fmt ' chunk")
    if fmt_code != 1:  # PCM
        raise ValueError("Only PCM format supported")
    if require_mono and channels != 1:
        raise ValueError("Only mono audio supported")
    if bits != 16:
        raise ValueError("Only 16-bit samples supported")

    # data chunk
    data_seek = 36
    while data_seek < len(wav_bytes):
        chunk_id, chunk_size = struct.unpack("<4sI", wav_bytes[data_seek : data_seek + 8])
        if chunk_id == b"data":
            data_start = data_seek + 8
            data_end = data_start + chunk_size
            if data_end > len(wav_bytes):
                raise ValueError("data chunk exceeds file size")
            pcm = wav_bytes[data_start:data_end]
            return WavHeader(pcm, rate, channels, bits)
        data_seek += 8 + chunk_size

    raise ValueError("Missing 'data' chunk")


def build_wav(pcm: bytes, rate: int) -> bytes:
    """Build WAV bytes from raw PCM (16-bit little-endian, mono)."""
    # RIFF header
    riff_size = 36 + len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        1,  # mono
        rate,
        rate * 2,  # avg bytes/sec (16-bit mono)
        2,  # block align
        16,  # bits per sample
        b"data",
        len(pcm),
    )
    return header + pcm


def rms(pcm16: bytes) -> int:
    """Compute RMS amplitude of 16-bit PCM (returns 0-32768)."""
    if len(pcm16) % 2 != 0:
        raise ValueError("PCM length must be even")
    samples = struct.unpack(f"<{len(pcm16)//2}h", pcm16)
    sum_sq = 0
    count = 0
    for s in samples:
        sum_sq += s * s
        count += 1
    if count == 0:
        return 0
    mean_sq = sum_sq / count
    return int((mean_sq**0.5))