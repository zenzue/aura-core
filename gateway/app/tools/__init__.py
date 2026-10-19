"""Tool registry and common exports."""

from .registry import ToolRegistry, build_registry
from .weather import Weather
from .local_time import get_local_time
from .network_status import DeviceStatusPlugin, NetworkStatusPlugin, SpeedtestPlugin
from .server_monitor import (
    ServerMonitor,
    get_server_status,
    get_service_health,
    get_cpu_usage,
    get_memory_usage,
    get_disk_usage,
    get_docker_status,
    get_container_status,
    get_http_endpoint_health,
    get_ssl_expiration,
    get_recent_alerts,
)

__all__ = [
    "ToolRegistry",
    "build_registry",
    "Weather",
    "get_local_time",
    "DeviceStatusPlugin",
    "NetworkStatusPlugin",
    "SpeedtestPlugin",
    "ServerMonitor",
    "get_server_status",
    "get_service_health",
    "get_cpu_usage",
    "get_memory_usage",
    "get_disk_usage",
    "get_docker_status",
    "get_container_status",
    "get_http_endpoint_health",
    "get_ssl_expiration",
    "get_recent_alerts",
]