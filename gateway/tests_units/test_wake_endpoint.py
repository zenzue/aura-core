"""Wake endpoint tests: honest behavior for disabled/no-stt/silence/match cases.

No real models: a stub STT provides deterministic transcripts.
"""

import base64

import httpx
import pytest

from app.app import create_app
from app.audio.wav_utils import build_wav
from app.config import Settings


class StubSTT:
    name = "stub"

    def __init__(self, text: str = "aura hello"):
        self._text = text
        self.calls = 0

    async def transcribe(self, wav: bytes, timeout_s: float = 20.0) -> str:
        self.calls += 1
        return self._text

    async def health(self, timeout_s: float = 5.0) -> bool:
        return True


def loud_wav(seconds_ms: int = 600, rate: int = 16000) -> bytes:
    """A sine-ish loud PCM blob so RMS gate passes."""
    n = max(1, rate * seconds_ms // 1000)
    pcm = bytearray()
    amp = 12000
    for i in range(n):
        v = amp if (i // 100) % 2 == 0 else -amp
        pcm += int(v).to_bytes(2, "little", signed=True)
    return build_wav(bytes(pcm), rate=rate)


def make_client(tmp_path, wake_enabled: bool, stt_text: str = "aura hello"):
    settings = Settings(
        wake_enabled=wake_enabled,
        gateway_data_dir=tmp_path / "gw",
        stt_provider="",
        tts_provider="",
        wake_regex=r"^aura\b",
        wake_min_rms=500.0,
        rate_limit_per_min=1000,
    )
    app = create_app(settings)
    app.state.stt = StubSTT(stt_text) if stt_text is not None else None

    class Client(httpx.AsyncClient):
        def __init__(self, app, *args, **kw):
            super().__init__(transport=httpx.ASGITransport(app=app),
                             base_url="http://testserver", *args, **kw)
            self.stub_app = app

    return Client(app)


@pytest.mark.asyncio
async def test_wake_disabled_reason(tmp_path):
    async with make_client(tmp_path, wake_enabled=False) as client:
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(loud_wav()).decode()})
        assert r.status_code == 200
        body = r.json()
        assert body["woke"] is False and body["reason"] == "disabled"


@pytest.mark.asyncio
async def test_wake_no_stt_honest_reason(tmp_path):
    async with make_client(tmp_path, wake_enabled=True, stt_text=None) as client:
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(loud_wav()).decode()})
        body = r.json()
        assert body["woke"] is False and "stt" in body["reason"]


@pytest.mark.asyncio
async def test_wake_match_and_nomatch(tmp_path):
    async with make_client(tmp_path, wake_enabled=True, stt_text="aura wake up") as client:
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(loud_wav()).decode()})
        body = r.json()
        assert body["woke"] is True
        assert body["reason"] == "match"
        assert body["text"] == "aura wake up"
        assert body["stt_provider"] == "stub"

    async with make_client(tmp_path, wake_enabled=True, stt_text="some random sentence") as client:
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(loud_wav()).decode()})
        body = r.json()
        assert body["woke"] is False and body["reason"] == "no match"


@pytest.mark.asyncio
async def test_wake_silence_gates_without_transcribe(tmp_path):
    async with make_client(tmp_path, wake_enabled=True, stt_text="aura hello") as client:
        stub = client.stub_app.state.stt
        quiet = build_wav(b"\x00\x00" * 16000, rate=16000)
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(quiet).decode()})
        body = r.json()
        assert body["woke"] is False and body["reason"] == "silence"
        assert stub.calls == 0


@pytest.mark.asyncio
async def test_wake_bad_base64_and_empty(tmp_path):
    async with make_client(tmp_path, wake_enabled=True) as client:
        r = await client.post("/v1/wake", json={"audio_b64": "!!!not base64!!!"})
        assert r.json()["reason"] == "invalid base64 audio"
        r = await client.post("/v1/wake", json={"audio_b64": ""})
        assert r.json()["reason"] == "empty audio"


@pytest.mark.asyncio
async def test_wake_bad_wav_no_models(tmp_path):
    async with make_client(tmp_path, wake_enabled=True) as client:
        r = await client.post("/v1/wake", json={"audio_b64": base64.b64encode(b"nope" * 100).decode()})
        assert "bad wav" in r.json()["reason"]
