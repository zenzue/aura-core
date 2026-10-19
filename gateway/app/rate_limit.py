import asyncio
import time
from collections import deque
from typing import Dict, Any

from litestar import Request
from litestar.middleware.rate_limit import RateLimit

from app.config import Settings


class RateLimiter:
    """Sliding window rate limiter per client IP."""

    def __init__(self, settings: Settings, key_func: callable) -> None:
        self.settings = settings
        self.key_func = key_func
        self.requests: Dict[str, deque] = {}  # key -> deque of timestamps

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed based on rate limit."""
        now = time.time()
        window_start = now - 60  # 60-second window
        
        if key not in self.requests:
            self.requests[key] = deque()
        
        # Clean old requests outside window
        while self.requests[key] and self.requests[key][0] < window_start:
            self.requests[key].popleft()
        
        # Check if within limit
        if len(self.requests[key]) >= self.settings.rate_limit_per_min:
            return False
        
        # Add current request
        self.requests[key].append(time.time())
        return True

    async def rate_limit_handler(self, request: Request, response_handler: callable) -> Any:
        """Rate limit middleware handler."""
        key = self.key_func(request)
        
        if not self.is_allowed(key):
            from litestar import Response
            return Response(
                content={"error": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        
        return await response_handler(request)