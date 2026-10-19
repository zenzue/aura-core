"""Server monitoring plugins (stub implementation when disabled)."""

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.tools.registry import BaseTool


@dataclass
class ServerTarget:
    name: str
    host: str
    port: int
    agent_token: str
    allowlist: List[str]


class ServerMonitor(BaseTool):
    name = "server_monitor"

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._targets: List[ServerTarget] = []

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Server monitoring tools",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        # This is a meta-tool; actual calls go to specific functions
        return {"ok": False, "error": "Use specific server monitor functions"}


# Individual monitor functions (stub when disabled)
async def get_server_status() -> Dict[str, Any]:
    """Get overall server status."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_service_health() -> Dict[str, Any]:
    """Get service health."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_cpu_usage() -> Dict[str, Any]:
    """Get CPU usage."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_memory_usage() -> Dict[str, Any]:
    """Get memory usage."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_disk_usage() -> Dict[str, Any]:
    """Get disk usage."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_docker_status() -> Dict[str, Any]:
    """Get Docker status."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_container_status() -> Dict[str, Any]:
    """Get container status."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_http_endpoint_health() -> Dict[str, Any]:
    """Get HTTP endpoint health."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_ssl_expiration() -> Dict[str, Any]:
    """Get SSL certificate expiration."""
    return {"ok": False, "error": "Server monitoring disabled"}


async def get_recent_alerts() -> Dict[str, Any]:
    """Get recent alerts."""
    return {"ok": False, "error": "Server monitoring disabled"}


# Load config helper (for future use)
def load_config() -> List[ServerTarget]:
    """Load server monitoring config from file."""
    config_path = os.getenv("SERVER_MONITOR_CONFIG", "config/server_monitoring.yaml")
    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f)
            targets = []
            for server in data.get("servers", []):
                targets.append(
                    ServerTarget(
                        name=server["name"],
                        host=server["host"],
                        port=server["port"],
                        agent_token=server["agent_token"],
                        allowlist=server["allowlist"],
                    )
                )
            return targets
    except Exception:
        return []