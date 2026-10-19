"""Network diagnostics plugins (device status, network status, speedtest)."""

import asyncio
import socket
import time
import httpx
from typing import Any, Callable, Dict

from app.config import Settings
from app.schemas import DeviceStats
from app.tools.registry import BaseTool


class DeviceStatusPlugin(BaseTool):
    name = "device_status"

    def __init__(self, devstats: Callable[[], DeviceStats | None] | None = None):
        super().__init__()
        self.devstats = devstats

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Get device status (battery, IP, etc)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        if self.devstats is None:
            return {"ok": False, "error": "Device stats not available"}
        try:
            stats = self.devstats()
            if stats is None:
                return {"ok": False, "error": "Device offline"}
            return {"ok": True, "stats": stats.model_dump()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class NetworkStatusPlugin(BaseTool):
    name = "network_status"

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Get network status (DNS, gateway DNS test)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        """Test DNS resolution of gateway host."""
        try:
            # Test DNS for gateway host (self)
            await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, "127.0.0.1"),
                timeout=timeout_s,
            )
            return {
                "ok": True,
                "gateway_dns_ok": True,
                "note": "RSSI is link quality, not throughput",
            }
        except Exception as e:
            return {"ok": True, "gateway_dns_ok": False, "error": str(e)}


class SpeedtestPlugin(BaseTool):
    name = "speedtest"

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._last_test_time = 0  # token-bucket: once per 600s

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Run network speedtest (HTTPS download)",
            "parameters": {
                "type": "object",
                "properties": {
                    "size_kb": {
                        "type": "integer",
                        "description": "Download size in KB (1024-5120, default 1024)",
                        "minimum": 1024,
                        "maximum": 5120,
                        "default": 1024,
                    },
                },
                "required": [],
            },
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        size_kb = args.get("size_kb", 1024)
        size_bytes = size_kb * 1024

        # Token-bucket: once per 600 seconds
        now = time.time()
        if now - self._last_test_time < 600:
            return {"ok": False, "error": "Rate limit: once per 600 seconds"}
        self._last_test_time = now

        try:
            url = f"https://speed.cloudflare.com/__down?bytes={size_bytes}"
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                start = time.perf_counter()
                resp = await client.get(url)
                resp.raise_for_status()
                data = await resp.aread()  # full bytes
                elapsed = time.perf_counter() - start

                if len(data) != size_bytes:
                    return {"ok": False, "error": "Download size mismatch"}

                mbps = (size_bytes * 8) / (elapsed * 1_000_000)  # megabits/sec
                return {
                    "ok": True,
                    "bytes": len(data),
                    "seconds": elapsed,
                    "mbps": round(mbps, 2),
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}