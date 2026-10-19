import functools
from typing import Any, Callable

from litestar import Request, Response
from litestar.middleware import MiddlewareProtocol
from litestar.types import ASGIApp, Scope, Receive, Send

from app.config import Settings


class AuthMiddleware(MiddlewareProtocol):
    """Authentication middleware for AURA Gateway."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auth_required = settings.auth_required

    async def __call__(
        self, app: ASGIApp, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process each request through authentication middleware."""
        request = Request(scope)
        
        # Skip authentication for health check
        if request.url.path in ["/healthz", "/docs", "/openapi.json"]:
            await app(scope, receive, send)
            return
            
        # Check authentication
        if self.auth_required:
            auth_header = request.headers.get("X-AURA-Token")
            if not auth_header or auth_header != self.settings.device_auth_token:
                response = Response(
                    content={"error": "Invalid or missing authentication token"},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        
        # Dev mode warning (one-time)
        if not self.auth_required and request.url.path not in ["/healthz", "/docs", "/openapi.json"]:
            if not hasattr(self, '_dev_warning_logged'):
                self._dev_warning_logged = True
                print("WARNING: Running in development mode - authentication disabled")
        
        await app(scope, receive, send)


def require_auth(settings: Settings) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require authentication on specific routes."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("X-AURA-Token")
            if settings.auth_required and (
                not auth_header or auth_header != settings.device_auth_token
            ):
                from litestar import Response
                return Response(
                    content={"error": "Invalid or missing authentication token"},
                    status_code=401,
                )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator