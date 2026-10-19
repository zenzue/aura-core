import asyncio
import logging
from typing import Any, Dict, List, Optional

from litestar import Litestar, Request, Response
from litestar.di import Provide
from litestar.openapi.config import OpenAPIConfig
from litestar.middleware.cors import CORSMiddleware
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.plugins import InitPluginProtocol

from app.api import routes
from app.auth import AuthMiddleware
from app.config import Settings
from app.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


class OptionalModulePlugin(InitPluginProtocol):
    """Plugin to handle optional modules with fail-open behavior."""

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self.optional_modules: Dict[str, Any] = {}

    async def load_audio(self) -> None:
        """Load audio module factories with optional import."""
        try:
            from app.audio import build_stt, build_tts
            self.optional_modules["stt"] = build_stt(self.settings)
            self.optional_modules["tts"] = build_tts(self.settings)
            logger.info("Audio modules loaded successfully")
        except ImportError as e:
            logger.warning(f"Audio modules not available: {e}")
            self.optional_modules["stt"] = None
            self.optional_modules["tts"] = None

    async def load_tools(self) -> None:
        """Load tools registry with optional import."""
        try:
            from app.tools import build_registry
            self.optional_modules["tools"] = build_registry(self.settings)
            logger.info("Tools registry loaded successfully")
        except ImportError as e:
            logger.warning(f"Tools registry not available: {e}")
            self.optional_modules["tools"] = None

    async def load_memory(self) -> None:
        """Load memory store with optional import."""
        try:
            from app.memory import MemoryStore
            self.optional_modules["memory"] = MemoryStore(self.settings)
            await self.optional_modules["memory"].ensure_schema()
            logger.info("Memory store loaded successfully")
        except ImportError as e:
            logger.warning(f"Memory store not available: {e}")
            self.optional_modules["memory"] = None

    async def load_providers(self) -> None:
        """Load LLM providers."""
        try:
            from app.providers import build_llm
            self.optional_modules["llm"] = build_llm(self.settings)
            logger.info("LLM provider loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load LLM provider: {e}")
            self.optional_modules["llm"] = None

    async def init(self, app: Litestar) -> None:
        """Initialize optional modules during app startup."""
        # Load all optional modules concurrently
        await asyncio.gather(
            self.load_audio(),
            self.load_tools(),
            self.load_memory(),
            self.load_providers(),
        )

        # Set state on app
        app.state.settings = self.settings
        app.state.stt = self.optional_modules["stt"]
        app.state.tts = self.optional_modules["tts"]
        app.state.tools = self.optional_modules["tools"]
        app.state.memory = self.optional_modules["memory"]
        app.state.llm = self.optional_modules["llm"]
        app.state.devstats = {}

        logger.info("AURA Gateway initialized successfully")


def create_app(settings: Settings) -> Litestar:
    """Create and configure the Litestar application."""
    
    # Initialize plugin for optional modules
    optional_plugin = OptionalModulePlugin(settings)
    
    # Rate limit configuration
    rate_limit_config = RateLimitConfig(
        rate_limiter=RateLimiter(
            settings=settings,
            key_func=lambda request: request.client.host or "unknown",
        ),
        default_limit=settings.rate_limit_per_min,
    )
    
    # OpenAPI configuration
    openapi_config = OpenAPIConfig(
        title="AURA Gateway API",
        version="1.0.0",
        description="AURA Gateway core API documentation",
    )
    
    # CORS middleware for development
    cors_config = CORSMiddleware(
        allow_origins=["*"],  # Restrict in production
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    
    app = Litestar(
        route_handlers=routes,
        middleware=[
            AuthMiddleware(settings=settings),
            cors_config,
        ],
        rate_limit_config=rate_limit_config,
        openapi_config=openapi_config,
        plugins=[optional_plugin],
        dependencies={
            "settings": Provide(lambda: settings),
        },
    )
    
    return app