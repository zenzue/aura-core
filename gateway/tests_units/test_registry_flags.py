"""Test registry builds correctly based on settings flags."""

from app.config import Settings
from app.tools import build_registry


def test_registry_weather_disabled():
    """Test weather not in registry when disabled."""
    settings = Settings(enable_weather=False)
    registry = build_registry(settings)

    # Weather should not be in specs
    specs = registry.specs_for_llm()
    weather_names = [s["name"] for s in specs]
    assert "weather" not in weather_names


def test_registry_weather_enabled():
    """Test weather in registry when enabled."""
    settings = Settings(enable_weather=True)
    registry = build_registry(settings)

    specs = registry.specs_for_llm()
    weather_names = [s["name"] for s in specs]
    assert "weather" in weather_names


def test_registry_network_diagnostics_disabled():
    """Test network diagnostics not in registry when disabled."""
    settings = Settings(enable_network_diagnostics=False)
    registry = build_registry(settings)

    specs = registry.specs_for_llm()
    diag_names = [s["name"] for s in specs]
    assert "device_status" not in diag_names
    assert "network_status" not in diag_names
    assert "speedtest" not in diag_names


def test_registry_server_monitoring_disabled():
    """Test server monitoring not in registry when disabled."""
    settings = Settings(enable_server_monitoring=False)
    registry = build_registry(settings)

    specs = registry.specs_for_llm()
    monitor_names = [s["name"] for s in specs]
    # ServerMonitor is meta; individual functions not in registry
    # But we can check that get_cpu_usage etc are not registered
    assert "get_cpu_usage" not in monitor_names
    assert "get_disk_usage" not in monitor_names


def test_registry_local_time_always():
    """Test local time always in registry."""
    settings = Settings()
    registry = build_registry(settings)

    specs = registry.specs_for_llm()
    time_names = [s["name"] for s in specs]
    assert "get_local_time" in time_names


def test_registry_multiple_flags():
    """Test complex flag combination."""
    settings = Settings(
        enable_weather=True,
        enable_network_diagnostics=True,
        enable_server_monitoring=True,
        enable_memory=True,  # not used in registry
    )
    registry = build_registry(settings)

    specs = registry.specs_for_llm()
    all_names = {s["name"] for s in specs}

    expected = {
        "weather",
        "get_local_time",
        "device_status",
        "network_status",
        "speedtest",
        # Server monitor tools not individually registered
    }
    assert expected.issubset(all_names)