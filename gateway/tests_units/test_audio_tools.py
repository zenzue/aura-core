"""Unit tests for gateway services: wav utils, local time, registry, weather parsing, memory."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.audio.wav_utils import build_wav, parse_wav, rms
from app.config import Settings
from app.memory.store import MemoryStore
from app.tools import build_registry
from app.tools.local_time import LocalTimePlugin
from app.tools.registry import ToolRegistry
from app.tools.weather import Weather, WEATHER_CODE_MAP


# ---------- wav_utils ----------

def test_build_parse_roundtrip():
    pcm = bytes([0x00, 0x80] * 100)  # full negative scale alternating
    wav = build_wav(pcm, rate=16000)
    header = parse_wav(wav)
    assert header.rate == 16000
    assert header.channels == 1
    assert header.bits == 16
    assert header.pcm == pcm


def test_parse_rejects_non_riff():
    with pytest.raises(ValueError):
        parse_wav(b"MDC1" + b"\x00" * 40)


def test_rms_values():
    assert rms(b"") == 0
    # full-scale alternating
    pcm = b"\xff\x7f" + b"\x00\x80"
    assert rms(pcm) == 32767
    assert rms(b"\x00\x00" * 10) == 0


def test_rms_odd_length_raises():
    with pytest.raises(ValueError):
        rms(b"\x00\x01\x02")


# ---------- local time ----------

@pytest.mark.asyncio
async def test_local_time_tool():
    plugin = LocalTimePlugin(Settings())
    specs = plugin.spec()
    assert "timezone" in specs["parameters"]["properties"]

    result = await plugin.call({}, timeout_s=5.0)
    assert result["ok"] is True
    assert "iso" in result and "human" in result
    from datetime import datetime

    datetime.fromisoformat(result["iso"])


@pytest.mark.asyncio
async def test_local_time_invalid_timezone_returns_error():
    plugin = LocalTimePlugin(Settings())
    result = await plugin.call({"timezone": "Not/AZone"}, timeout_s=5.0)
    assert result["ok"] is False


# ---------- registry ----------

def test_registry_flags():
    settings = Settings(
        enable_weather=False,
        enable_network_diagnostics=True,
        enable_server_monitoring=False,
    )
    registry = build_registry(settings)
    specs = registry.specs_for_llm()
    names = {s["name"] for s in specs}
    assert "get_local_time" in names
    assert "device_status" in names
    assert "network_status" in names
    assert "weather" not in names
    assert "server_monitor" not in names


def test_registry_flagless_minimal():
    settings = Settings(
        enable_weather=False,
        enable_network_diagnostics=False,
        enable_server_monitoring=False,
    )
    registry = build_registry(settings)
    names = {s["name"] for s in registry.specs_for_llm()}
    assert names == {"get_local_time"}


def test_registry_duplicate_register_rejected():
    reg = ToolRegistry()
    plugin = LocalTimePlugin(Settings())
    reg.register(plugin)
    with pytest.raises(ValueError):
        reg.register(LocalTimePlugin(Settings()))


@pytest.mark.asyncio
async def test_registry_call_never_raises_and_keys_only_audit():
    settings = Settings(enable_weather=False, enable_network_diagnostics=False,
                        enable_server_monitoring=False)
    registry = build_registry(settings)

    # missing tool -> ok:false
    result = await registry.call("no_such", {"secret_arg": "value"}, timeout_s=1.0)
    assert result["ok"] is False
    assert "not found" in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_registry_timeout_is_reported():
    registry = ToolRegistry()

    class Slow(LocalTimePlugin):
        name = "slow_tool"

        async def call(self, args, timeout_s=10.0):
            await asyncio.sleep(5)
            return {"ok": True}

    registry.register(Slow(Settings()))
    result = await registry.call("slow_tool", {}, timeout_s=0.05)
    assert result["ok"] is False
    assert "timeout" in str(result).lower()


# ---------- weather parsing (mocked HTTP) ----------

@pytest.mark.asyncio
async def test_weather_unknown_location_honest_error():
    weather = Weather(Settings(weather_default_location="Bangkok"))
    payload = {"results": []}

    def handler(request):
        return __import__("httpx").Response(200, json=payload)

    import httpx

    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    with patch("app.tools.weather.httpx.AsyncClient", factory):
        result = await weather.call({"location": "NowhereCity"}, timeout_s=5.0)
    assert result["ok"] is False
    assert "not found" in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_weather_parse_real_shape():
    weather = Weather(Settings())
    import httpx

    def handler(request):
        url = str(request.url)
        if "geocoding" in url:
            return httpx.Response(200, json={"results": [{"name": "Bangkok", "latitude": 13.75, "longitude": 100.5}]})
        return httpx.Response(200, json={
            "latitude": 13.75,
            "longitude": 100.5,
            "current": {"temperature_2m": 30.0, "relative_humidity_2m": 80,
                        "weather_code": 81, "wind_speed_10m": 5.0},
            "daily": {"time": ["2026-10-19", "2026-10-20"], "temperature_2m_max": [33.0, 31.0],
                      "temperature_2m_min": [25.0, 24.0]},
        })

    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    with patch("app.tools.weather.httpx.AsyncClient", factory):
        result = await weather.call({"location": "Bangkok"}, timeout_s=5.0)
    assert result["ok"] is True
    assert result["current"]["temperature"] == 30.0
    assert result["current"]["weather"] == WEATHER_CODE_MAP[81]


# ---------- memory store ----------

def test_memory_remember_and_recent(tmp_path):
    settings = Settings(enable_memory=True, summarise_every=4, gateway_data_dir=tmp_path)
    store = MemoryStore(settings)
    store.remember("c1", {"role": "user", "content": "hi"})
    store.remember("c1", {"role": "assistant", "content": "hello"})
    assert store.count_messages("c1") == 2
    messages = store.get_messages("c1")
    assert messages[0]["content"] == "hi"


def test_memory_forget_one_and_all(tmp_path):
    settings = Settings(enable_memory=True, summarise_every=100, gateway_data_dir=tmp_path)
    store = MemoryStore(settings)
    store.remember("c1", {"id": "m1", "role": "user", "content": "a"})
    store.remember("c1", {"id": "m2", "role": "user", "content": "b"})
    assert store.forget("c1", message_id="m1") == 1
    assert store.count_messages("c1") == 1
    assert store.forget("c1", message_id=None) == 1


@pytest.mark.asyncio
async def test_memory_maybe_summarize_triggers_at_threshold(tmp_path):
    settings = Settings(enable_memory=True, summarise_every=3, gateway_data_dir=tmp_path)
    store = MemoryStore(settings)
    for i in range(3):
        store.remember("c1", {"role": "user", "content": f"m{i}"})

    class FakeLLM:
        async def generate_reply(self, messages, tools=None, system_prompt=None):
            return {"spoken_text": "They talked about m0 m1 m2.", "emotion": "neutral"}

    summary = await store.maybe_summarize(FakeLLM(), "c1")
    assert summary == "They talked about m0 m1 m2."
    roles = [m["role"] for m in store.get_messages("c1")]
    assert "system" in roles


@pytest.mark.asyncio
async def test_memory_maybe_summarize_below_threshold_returns_none(tmp_path):
    settings = Settings(enable_memory=True, summarise_every=10, gateway_data_dir=tmp_path)
    store = MemoryStore(settings)
    store.remember("c1", {"role": "user", "content": "hello"})

    class NeverLLM:
        async def generate_reply(self, *a, **k):
            raise AssertionError("must not be called below threshold")

    assert await store.maybe_summarize(NeverLLM(), "c1") is None


@pytest.mark.asyncio
async def test_memory_summarize_llm_failure_returns_none_no_raise(tmp_path):
    settings = Settings(enable_memory=True, summarise_every=1, gateway_data_dir=tmp_path)
    store = MemoryStore(settings)
    store.remember("c1", {"role": "user", "content": "hello"})

    class BoomLLM:
        async def generate_reply(self, *a, **k):
            raise RuntimeError("llm down")

    assert await store.maybe_summarize(BoomLLM(), "c1") is None
