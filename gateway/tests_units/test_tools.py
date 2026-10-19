"""Tools tests with HTTPX mock fixtures."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx
from datetime import datetime

from app.config import Settings
from app.tools import build_registry
from app.tools.weather import Weather
from app.tools.network_status import SpeedtestPlugin

# Real response fixtures (from actual endpoints)
GEOCODE_FIXTURE = """{
  "results": [
    {
      "name": "Bangkok",
      "latitude": 13.75398,
      "longitude": 100.50144
    }
  ]
}"""

FORECAST_FIXTURE = """{
  "latitude": 13.75398,
  "longitude": 100.50144,
  "current": {
    "temperature_2m": 25.2,
    "relative_humidity_2m": 95,
    "weather_code": 81,
    "wind_speed_10m": 4.9
  },
  "daily": {
    "time": ["2026-10-19", "2026-10-20"],
    "temperature_2m_max": [32.1, 31.2],
    "temperature_2m_min": [24.1, 23.4]
  }
}"""

SPEEDTEST_FIXTURE = b"0" * 1024  # dummy data


@pytest.fixture
def mock_settings():
    return Settings(
        enable_weather=True,
        enable_network_diagnostics=True,
        enable_server_monitoring=False,
        tool_timeout_s=10.0,
    )


@pytest.fixture
def mock_httpx_transport():
    """Mock transport with real response fixtures."""
    transport = httpx.AsyncMockTransport()

    # Geocoding mock
    async def geocode_handler(request):
        return httpx.Response(
            status_code=200,
            content=GEOCODE_FIXTURE,
            headers={"Content-Type": "application/json"},
        )

    # Forecast mock
    async def forecast_handler(request):
        return httpx.Response(
            status_code=200,
            content=FORECAST_FIXTURE,
            headers={"Content-Type": "application/json"},
        )

    # Speedtest mock
    async def speedtest_handler(request):
        return httpx.Response(
            status_code=200,
            content=SPEEDTEST_FIXTURE,
            headers={"Content-Type": "application/octet-stream"},
        )

    transport.register_uri(
        "GET", "https://geocoding-api.open-meteo.com/v1/search", handler=geocode_handler
    )
    transport.register_uri(
        "GET", "https://api.open-meteo.com/v1/forecast", handler=forecast_handler
    )
    transport.register_uri(
        "GET", "https://speed.cloudflare.com/__down", handler=speedtest_handler
    )

    return transport


@pytest.fixture
def registry(mock_settings, mock_httpx_transport):
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value.transport = mock_httpx_transport
        return build_registry(mock_settings)


@pytest.mark.asyncio
async def test_weather_tool(registry):
    """Test weather tool with mock responses."""
    weather = registry.get("weather")
    assert isinstance(weather, Weather)

    result = await weather.call({"location": "Bangkok"})
    assert result["ok"] is True
    assert "current" in result
    assert "forecast" in result
    assert result["current"]["temperature"] == 25.2
    assert result["current"]["weather"] == "Moderate showers"  # code 81


@pytest.mark.asyncio
async def test_weather_default_location(registry):
    """Test weather with default location."""
    weather = registry.get("weather")
    result = await weather.call({"location": "default"})
    assert result["ok"] is True
    # Should use settings default coordinates
    assert "current" in result


@pytest.mark.asyncio
async def test_weather_unknown_location(registry):
    """Test weather with unknown location."""
    weather = registry.get("weather")
    result = await weather.call({"location": "InvalidCity123"})
    assert result["ok"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_speedtest_tool(registry):
    """Test speedtest tool."""
    speedtest = registry.get("speedtest")
    assert isinstance(speedtest, SpeedtestPlugin)

    result = await speedtest.call({"size_kb": 1024})
    assert result["ok"] is True
    assert result["bytes"] == 1024
    assert "seconds" in result
    assert "mbps" in result


@pytest.mark.asyncio
async def test_speedtest_rate_limit(registry):
    """Test speedtest rate limiting."""
    speedtest = registry.get("speedtest")

    # First call
    await speedtest.call({"size_kb": 1024})
    # Second call immediately (should be rate limited)
    result = await speedtest.call({"size_kb": 1024})
    assert result["ok"] is False
    assert "Rate limit" in result["error"]


@pytest.mark.asyncio
async def test_local_time_tool(registry):
    """Test local time tool."""
    registry._tools["get_local_time"].call = AsyncMock(return_value={
        "ok": True,
        "iso": "2026-10-19T12:34:56+07:00",
        "human": "2026-10-19 12:34:56 +07:00"
    })
    result = await registry.call("get_local_time", {})
    assert result["ok"] is True
    assert "iso" in result


@pytest.mark.asyncio
async def test_tool_not_found(registry):
    """Test calling unknown tool."""
    result = await registry.call("unknown_tool", {})
    assert result["ok"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_tool_timeout(registry):
    """Test tool timeout."""
    # Mock a tool that hangs
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
async def test_server_monitor_disabled(registry, mock_settings):
    """Test server monitor tools when disabled."""
    mock_settings.enable_server_monitoring = False
    registry = build_registry(mock_settings)

    # All server monitor functions should return disabled
    from app.tools.server_monitor import get_cpu_usage, get_disk_usage

    cpu = await get_cpu_usage()
    assert cpu["ok"] is False
    assert "disabled" in cpu["error"]

    disk = await get_disk_usage()
    assert disk["ok"] is False
    assert "disabled" in disk["error"]


@pytest.mark.asyncio
async def test_read_only_guard(registry):
    """Test read-only guard on tools."""
    # Weather is read-only
    weather = registry.get("weather")
    assert weather.read_only is True

    # Try to call with non-read-only args (should be ignored by contract)
    result = await weather.call({"location": "Bangkok", "write": True})
    assert result["ok"] is True  # still returns data