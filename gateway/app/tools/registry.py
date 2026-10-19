"""Tool registry with plugin system and audit logging."""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List

from app.config import Settings
from app.schemas import ToolPlugin, ToolCall

logger = logging.getLogger("gateway.tools")


class ToolRegistry:
    """Registry of available tools with async call wrapper."""

    def __init__(self):
        self._tools: Dict[str, ToolPlugin] = {}
        self._names: set[str] = set()

    def register(self, plugin: ToolPlugin):
        if plugin.name in self._names:
            raise ValueError(f"Tool already registered: {plugin.name}")
        self._tools[plugin.name] = plugin
        self._names.add(plugin.name)

    def get(self, name: str) -> ToolPlugin:
        if name not in self._names:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def specs_for_llm(self) -> List[Dict[str, Any]]:
        """Return LLM-readable tool specs (function calling)."""
        specs = []
        for name in sorted(self._names):
            tool = self._tools[name]
            spec = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.spec().get("description", ""),
                    "parameters": tool.spec().get("parameters", {}),
                },
            }
            specs.append(spec)
        return specs

    async def call(self, name: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        """Call tool async; return dict {ok,...} never raises."""
        start = time.perf_counter()
        try:
            tool = self.get(name)
            # Audit log: name, arg KEYS only (avoid sensitive data), elapsed ms
            logger.info(
                "tool_call",
                extra={
                    "tool": name,
                    "args_keys": list(args.keys()),
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                },
            )
            result = await asyncio.wait_for(tool.call(args, timeout_s=timeout_s), timeout=timeout_s)
            elapsed = time.perf_counter() - start
            return {"ok": True, "result": result, "elapsed_ms": int(elapsed * 1000)}
        except asyncio.TimeoutError:
            logger.warning("tool_timeout", extra={"tool": name, "timeout_s": timeout_s})
            return {"ok": False, "error": "timeout"}
        except Exception as e:
            logger.exception("tool_error", extra={"tool": name, "error": str(e)})
            return {"ok": False, "error": str(e)}


def build_registry(settings: Settings, devstats: Callable[[], Any] | None = None) -> ToolRegistry:
    """Factory: build registry from settings flags."""
    registry = ToolRegistry()

    # Weather
    if settings.enable_weather:
        from .weather import Weather

        registry.register(Weather())

    # Local time (always available)
    from .local_time import LocalTimePlugin

    registry.register(LocalTimePlugin())

    # Network diagnostics
    if settings.enable_network_diagnostics:
        from .network_status import DeviceStatusPlugin, NetworkStatusPlugin, SpeedtestPlugin

        registry.register(DeviceStatusPlugin(devstats))
        registry.register(NetworkStatusPlugin())
        registry.register(SpeedtestPlugin())

    # Server monitoring
    if settings.enable_server_monitoring:
        from .server_monitor import ServerMonitor

        registry.register(ServerMonitor())

    return registry


# Plugin base for easier registration
class BaseTool(ToolPlugin):
    read_only = True

    def __init__(self, **kwargs: Any):
        super().__init__()
        self.name = self.__class__.__name__.lower().replace("plugin", "")
        self.read_only = self.__class__.read_only

    def spec(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    async def call(self, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError