"""Litestar application factory. Providers constructed synchronously at create
time so ASGI test transports work without lifespan; missing providers become
None and endpoints answer with clear errors, never fake replies."""
from __future__ import annotations

import logging
from typing import Any

from litestar import Litestar
from litestar.openapi.config import OpenAPIConfig

from app.api import build_routes
from app.auth import AuthMiddleware
from app.config import Settings
from app.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


def _build_optional(label: str, fn, *args) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s unavailable: %s", label, exc)
        return None


def create_app(settings: Settings) -> Litestar:
    from app.audio import build_stt, build_tts
    from app.providers import build_llm
    from app.tools import build_registry

    devstats: dict[str, Any] = {}

    llm = _build_optional("llm", build_llm, settings)
    stt = _build_optional("stt", build_stt, settings)
    tts = _build_optional("tts", build_tts, settings)
    tools = _build_optional("tools", build_registry, settings, lambda: dict(devstats))

    memory = None
    if settings.enable_memory:
        try:
            from app.memory import MemoryStore
            memory = MemoryStore(settings, llm=llm)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory store unavailable: %s", exc)

    app = Litestar(
        route_handlers=build_routes(),
        middleware=[
            (RateLimitMiddleware, {"settings": settings}),
            (AuthMiddleware, {"settings": settings}),
        ],
        openapi_config=OpenAPIConfig(title="AURA Gateway API", version="1.0.0"),
        debug=False,
    )

    app.state.settings = settings
    app.state.devstats = devstats
    app.state.llm = llm
    app.state.stt = stt
    app.state.tts = tts
    app.state.tools = tools
    app.state.memory = memory

    logger.info(
        "AURA gateway ready: llm=%s stt=%s tts=%s tools=%s memory=%s",
        llm is not None, stt is not None, tts is not None,
        tools is not None, memory is not None,
    )
    return app
