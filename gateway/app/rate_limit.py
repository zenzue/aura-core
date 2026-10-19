"""Per-client sliding-window rate limiting as a custom ASGI middleware."""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any, Deque, Dict, Tuple

from litestar.middleware.base import MiddlewareProtocol
from litestar.types import ASGIApp, Receive, Scope, Send

from app.config import Settings

BYPASS_PATHS = {"/healthz", "/docs", "/openapi.json", "/schema"}


class RateLimiter:
    """Sliding window (60s) limiter keyed by string."""

    def __init__(self, max_per_min: int) -> None:
        self.max_per_min = max_per_min
        self._hits: Dict[str, Deque[float]] = {}

    def is_allowed(self, key: str) -> bool:
        if self.max_per_min <= 0:
            return True
        now = time.monotonic()
        dq = self._hits.setdefault(key, deque())
        while dq and dq[0] < now - 60.0:
            dq.popleft()
        if len(dq) >= self.max_per_min:
            return False
        dq.append(now)
        return True


class RateLimitMiddleware(MiddlewareProtocol):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.limiter = RateLimiter(settings.rate_limit_per_min)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> Any:
        if scope["type"] != "http" or scope.get("path") in BYPASS_PATHS:
            return await self.app(scope, receive, send)
        client = scope.get("client")
        key: Tuple[str, int] = client if client else ("unknown", 0)
        key_str = f"{key[0]}:{key[1]}" if isinstance(key, tuple) else str(key)
        if not self.limiter.is_allowed(key_str):
            body = json.dumps({"detail": "rate limit exceeded"}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [(b"content-type", b"application/json"),
                            (b"retry-after", b"60"),
                            (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return
        return await self.app(scope, receive, send)
