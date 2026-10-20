import asyncio
import httpx
import pytest

from app.app import create_app
from app.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        gateway_data_dir=tmp_path / "gw",
        ai_provider="ollama",
        ollama_model="test-model",
        gemini_api_key="test-key",
        openai_api_key="test-key",
        rate_limit_per_min=1000,
        max_audio_bytes=1024,
        history_max_messages=10,
        enable_memory=True,
        debug=True,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
async def client(settings: Settings):
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.app = app  # tests inspect client.app.state
        yield client
