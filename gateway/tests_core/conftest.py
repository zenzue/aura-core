import pytest
from typing import Any, Dict, Generator

from litestar import Litestar

from app.app import create_app
from app.config import Settings, load_settings


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Event loop fixture."""
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings() -> Settings:
    """Test settings fixture."""
    return Settings(
        auth_required=False,  # Disable auth for tests
        ai_provider="ollama",  # Use ollama for tests
        ollama_model="test-model",
        gemini_api_key="test-key",
        openai_api_key="test-key",
        rate_limit_per_min=1000,  # High limit for tests
        max_audio_bytes=1024,
        history_max_messages=10,
        enable_memory=True,
        debug=True,
    )


@pytest.fixture
def app(settings: Settings) -> Litestar:
    """Test app fixture."""
    return create_app(settings)


@pytest.fixture
def client(settings: Settings) -> Any:
    """Test client fixture using httpx."""
    import httpx
    
    app = create_app(settings)
    
    # Use ASGITransport for testing
    transport = httpx.ASGITransport(app=app, lifespan=True)
    
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")