"""Bearer-token auth middleware. Token compared against settings.device_auth_token."""
from __future__ import annotations

from litestar import Request, Response
from litestar.middleware.base import MiddlewareProtocol
from litestar.types import ASGIApp, Receive, Scope, Send

from app.config import Settings

BYPASS_PATHS = {"/healthz", "/docs", "/openapi.json", "/schema"}


class AuthMiddleware(MiddlewareProtocol):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.auth_required = settings.auth_required

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> ASGIApp:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path in BYPASS_PATHS or not self.auth_required:
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        token = headers.get(b"x-aura-token", b"").decode()
        if token != self.settings.device_auth_token:
            response = Response(
                content={"detail": "Invalid or missing authentication token"},
                status_code=401,
            )
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
