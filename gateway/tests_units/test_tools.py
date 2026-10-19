"""Tool tests: real plugins with mocked HTTP transports (no network)."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.tools import build_registry
from app.tools.weather import Weather
from app.tools.network_status import SpeedtestPlugin

GEOCODE_FIXTURE = {
    "results": [
        {"name": "Bangkok", "latitude": 13.75398, "longitude": 100.50144},
    ]
}

FORECAST_FIXTURE = {
    "latitude": 13.75398,
    "longitude": 100.50144,
    "current": {
        "temperature_2m": 25.2,
        "relative_humidity_2m": 95,
        "weather_code": 81,
        "wind_speed_10m": 4.9,
    },
    "daily": {
        "time": ["2026-10-19", "2026-10-20"],
        "temperature_2m_max": [32.1, 31.2],
        "temperature_2m_min": [24.1, 23.4],
    },
}


def _dispatch(request: httpx.Request) -> httpx.Response:
    host = request.url.host or ""
    if host == "geocoding-api.open-meteo.com":
        name = request.url.params.get("name", "")
        if name.lower() == "invalidcity123":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json=GEOCODE_FIXTURE)
    if host == "api.open-meteo.com":
        return httpx.Response(200, json=FORECAST_FIXTURE)
    if host.endswith("speed.cloudflare.com"):
        size = int(request.url.params.get("bytes", "1024"))
        return httpx.Response(200, content=b"0" * size)
    return httpx.Response(404, json={"detail": "unhandled mock host"})


@pytest.fixture
def mock_settings():
    return Settings(
        enable_weather=True,
        enable_network_diagnostics=True,
        enable_server_monitoring=False,
        tool_timeout_s=10.0,
    )


@pytest.fixture
def registry(mock_settings, monkeypatch):
    real_cls = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_cls(*args, transport=httpx.MockTransport(_dispatch), **kwargs)

    monkeypatch.setattr("app.tools.weather.httpx.AsyncClient", factory)
    monkeypatch.setattr("app.tools.network_status.httpx.AsyncClient", factory)
    return build_registry(mock_settings)


@pytest.mark.asyncio
async def test_weather_tool(registry):
    weather = registry.get("weather")
    assert isinstance(weather, Weather)

    result = await weather.call({"location": "Bangkok"}, timeout_s=5.0)
    assert result["ok"] is True
    assert "current" in result
    assert "forecast" in result
    assert result["current"]["temperature"] == 25.2
    assert result["current"]["weather"] == "Moderate showers"  # WMO code 81


@pytest.mark.asyncio
async def test_weather_default_location(registry):
    weather = registry.get("weather")
    result = await weather.call({"location": "default"}, timeout_s=5.0)
    assert result["ok"] is True
    assert "current" in result


@pytest.mark.asyncio
async def test_weather_unknown_location(registry):
    weather = registry.get("weather")
    result = await weather.call({"location": "InvalidCity123"}, timeout_s=5.0)
    assert result["ok"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_speedtest_tool(registry):
    speedtest = registry.get("speedtest")
    assert isinstance(speedtest, SpeedtestPlugin)

    result = await speedtest.call({"size_kb": 1024}, timeout_s=5.0)
    assert result["ok"] is True
    assert result["bytes"] == 1024 * 1024
    assert "seconds" in result
    assert "mbps" in result


@pytest.mark.asyncio
async def test_speedtest_rate_limit(registry):
    speedtest = registry.get("speedtest")
    speedtest._last_test_time = 0.0
    await speedtest.call({"size_kb": 1024}, timeout_s=5.0)
    result = await speedtest.call({"size_kb": 1024}, timeout_s=5.0)
    assert result["ok"] is False
    assert "Rate limit" in result["error"]


@pytest.mark.asyncio
async def test_local_time_tool(registry):
    registry._tools["get_local_time"].call = AsyncMock(return_value={
        "ok": True,
        "iso": "2026-10-19T12:34:56+07:00",
        "human": "2026-10-19 12:34:56 +07:00",
    })
    result = await registry.call("get_local_time", {}, timeout_s=5.0)
    assert result["ok"] is True
    assert "iso" in str(result["result"])


@pytest.mark.asyncio
async def test_tool_not_found(registry):
    result = await registry.call("unknown_tool", {}, timeout_s=5.0)
    assert result["ok"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_tool_timeout(registry):
    class SlowTool:
        name = "slow"
        read_only = True

        def spec(self):
            return {"description": "Slow tool", "parameters": {}}

        async def call(self, args, timeout_s):
            await asyncio.sleep(timeout_s * 2)
            return {"result": "done"}

    registry.register(SlowTool())
    result = await registry.call("slow", {}, timeout_s=0.1)
    assert result["ok"] is False
    assert "timeout" in result["error"]


@pytest.mark.asyncio
async def test_server_monitor_disabled():
    from app.tools.server_monitor import get_cpu_usage, get_disk_usage

    cpu = await get_cpu_usage()
    assert cpu["ok"] is False
    assert "disabled" in cpu["error"]

    disk = await get_disk_usage()
    assert disk["ok"] is False
    assert "disabled" in disk["error"]


@pytest.mark.asyncio
async def test_read_only_guard(registry):
    weather = registry.get("weather")
    assert weather.read_only is True
    for tool in registry._tools.values():
        assert tool.read_only is True
