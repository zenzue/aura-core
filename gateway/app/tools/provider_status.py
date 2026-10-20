"""Read-only diagnostic tools: gateway health + AI provider status.

Never fabricates: reports only measured values and real provider state.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from app.tools.registry import BaseTool

BOOT_TIME = time.monotonic()


class GatewayHealthPlugin(BaseTool):
    name = "get_gateway_health"
    read_only = True

    def __init__(self, devstats: Optional[Callable[[], Any]] = None) -> None:
        super().__init__()
        self._devstats = devstats or (lambda: {})

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Gateway uptime, uptime seconds and last device stats.",
            "parameters": {"type": "object", "properties": {}},
        }

    async def call(self, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        stats = {}
        try:
            stats = dict(self._devstats() or {})
        except Exception:  # noqa: BLE001
            pass
        uptime_s = int(time.monotonic() - BOOT_TIME)
        return {"ok": True, "result": {"uptime_s": uptime_s, "device_stats": stats}}


class AiProviderStatusPlugin(BaseTool):
    name = "get_ai_provider_status"
    read_only = True

    def __init__(self, service: Optional[Any] = None) -> None:
        super().__init__()
        self._service = service

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Active AI provider, model, health and failover chain.",
            "parameters": {"type": "object", "properties": {}},
        }

    async def call(self, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        svc = self._service
        if svc is None:
            return {"ok": True, "result": {"provider": "disabled"}}
        try:
            info = await svc.check_health(timeout_s=min(timeout_s, 10.0))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": info}
