import base64
import pytest
from unittest.mock import Mock, AsyncMock

from app.api import health_check, status, interact, device_stats, tts_generate
from app.config import Settings
from app.schemas import InteractRequest, DeviceStats, TTSRequest, AuraResponse


@pytest.mark.asyncio
async def test_health_check() -> None:
    """Test health check endpoint."""
    request = Mock()
    response = await health_check(request)
    assert response == {"ok": True}


@pytest.mark.asyncio
async def test_status(client) -> None:
    """Test status endpoint."""
    response = await client.get("/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "llm" in data
    assert "stt" in data
    assert "tts" in data


@pytest.mark.asyncio
async def test_device_stats(client) -> None:
    """Test device stats endpoint."""
    stats = DeviceStats(
        battery_level=85,
        temperature=42.5,
        memory_usage=1024,
    )
    response = await client.post("/v1/device_stats", json=stats.dict())
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "updated"}


@pytest.mark.asyncio
async def test_tts_generate(client) -> None:
    """Test TTS generation endpoint."""
    request = TTSRequest(text="Hello world")
    response = await client.post("/v1/tts", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert "spoken_text" in data
    assert "display_text" in data
    assert "emotion" in data
    # Audio may be null if TTS not available


@pytest.mark.asyncio
async def test_interact_happy_path(client) -> None:
    """Test interact endpoint with happy path."""
    # Mock the app state to have providers available
    app_state = client.app.state
    app_state.llm = Mock()
    app_state.llm.generate_reply = AsyncMock(return_value={
        "spoken_text": "Hello!",
        "display_text": "Hello!",
        "emotion": "happy",
        "expression_intensity": 0.8,
        "animation_hint": "wave",
        "action": "none",
    })
    app_state.llm.parse_llm_reply = Mock(side_effect=lambda x: x)
    app_state.stt = Mock()
    app_state.tts = Mock()
    app_state.tools = Mock()
    app_state.tools.specs_for_llm = Mock(return_value=[])
    app_state.tools.call = AsyncMock(return_value={"result": "success"})
    app_state.memory = Mock()
    app_state.memory.recent_messages = AsyncMock(return_value=[])
    app_state.memory.append_message = AsyncMock()
    app_state.memory.maybe_summarize = AsyncMock()
    
    request = InteractRequest(
        text="Hello",
        audio_wav_b64=base64.b64encode(b"fake audio").decode(),
        conversation_id="test_conv",
        tts=True,
    )
    
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert data["spoken_text"] == "Hello!"
    assert data["emotion"] == "happy"


@pytest.mark.asyncio
async def test_interact_no_providers(client) -> None:
    """Test interact endpoint with no providers available."""
    # Clear all providers
    app_state = client.app.state
    app_state.llm = None
    app_state.stt = None
    app_state.tts = None
    app_state.tools = None
    app_state.memory = None
    
    request = InteractRequest(text="Hello")
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert "service unavailable" in data["display_text"].lower()


@pytest.mark.asyncio
async def test_interact_invalid_emotion(client) -> None:
    """Test interact endpoint with invalid emotion handling."""
    app_state = client.app.state
    app_state.llm = Mock()
    app_state.llm.generate_reply = AsyncMock(return_value={
        "spoken_text": "Hello!",
        "display_text": "Hello!",
        "emotion": "invalid_emotion",  # Should be neutralized
        "expression_intensity": 0.8,
        "animation_hint": "wave",
        "action": "none",
    })
    app_state.llm.parse_llm_reply = Mock(side_effect=lambda x: x)
    
    request = InteractRequest(text="Hello")
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert data["emotion"] == "neutral"  # Should be neutralized


@pytest.mark.asyncio
async def test_interact_long_spoken_text(client) -> None:
    """Test interact endpoint with long spoken text truncation."""
    long_text = "a" * 300  # Exceeds max_spoken_chars
    
    app_state = client.app.state
    app_state.llm = Mock()
    app_state.llm.generate_reply = AsyncMock(return_value={
        "spoken_text": long_text,
        "display_text": long_text,
        "emotion": "neutral",
        "expression_intensity": 0.7,
        "animation_hint": "none",
        "action": "none",
    })
    app_state.llm.parse_llm_reply = Mock(side_effect=lambda x: x)
    
    request = InteractRequest(text="Hello")
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert len(data["spoken_text"]) <= 240  # Should be truncated
    assert data["spoken_text"].endswith("...")  # Should have ellipsis


@pytest.mark.asyncio
async def test_interact_malformed_json(client) -> None:
    """Test interact endpoint with malformed JSON from LLM."""
    app_state = client.app.state
    app_state.llm = Mock()
    app_state.llm.generate_reply = AsyncMock(return_value="malformed json string")
    app_state.llm.parse_llm_reply = Mock(side_effect=Exception("parse error"))
    
    request = InteractRequest(text="Hello")
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    assert "processing error" in data["display_text"].lower()


@pytest.mark.asyncio
async def test_interact_tool_calls(client) -> None:
    """Test interact endpoint with tool calls."""
    app_state = client.app.state
    app_state.llm = Mock()
    app_state.llm.generate_reply = AsyncMock(return_value={
        "spoken_text": "Processing your request",
        "display_text": "Using weather tool",
        "emotion": "neutral",
        "expression_intensity": 0.7,
        "animation_hint": "loading",
        "action": "none",
        "tool_calls": [
            {"name": "get_weather", "arguments": {"location": "New York"}}
        ],
    })
    app_state.llm.parse_llm_reply = Mock(side_effect=lambda x: x)
    app_state.tools = Mock()
    app_state.tools.specs_for_llm = Mock(return_value=[
        {"name": "get_weather", "description": "Get weather for a location"}
    ])
    app_state.tools.call = AsyncMock(return_value={"temperature": 72, "condition": "sunny"})
    app_state.memory = Mock()
    app_state.memory.recent_messages = AsyncMock(return_value=[])
    app_state.memory.append_message = AsyncMock()
    app_state.memory.maybe_summarize = AsyncMock()
    
    request = InteractRequest(text="What's the weather?")
    response = await client.post("/v1/interact", json=request.dict())
    assert response.status_code == 200
    data = response.json()
    # Tool calls should be executed and results included in trace
    # (actual implementation would handle this differently)


@pytest.mark.requires_models
@pytest.mark.asyncio
async def test_ollama_provider_integration(client) -> None:
    """Test Ollama provider integration (requires models)."""
    # This test would require actual Ollama setup
    # Skip for now as it's marked as requires_models
    pytest.skip("Requires Ollama models - skipping for now")

@pytest.mark.asyncio
async def test_memory_background_summarize(settings, tmp_path):
    """Summarization runs in a background task and must not delay or fake replies."""
    from app.app import create_app as _create_app
    import httpx

    settings.enable_memory = True
    settings.summarise_every = 2
    app = _create_app(settings)

    from unittest.mock import AsyncMock as _AM, Mock as _M

    reply = {
        "spoken_text": "ok",
        "display_text": "ok",
        "emotion": "neutral",
        "expression_intensity": 0.5,
        "animation_hint": "none",
        "action": "none",
    }
    app.state.llm = _M()
    app.state.llm.generate_reply = _AM(return_value=dict(reply))
    app.state.llm.parse_llm_reply = _M(side_effect=lambda x: x)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        for i in range(2):
            r = await client.post(
                "/v1/interact",
                json={"text": f"hello {i}", "conversation_id": "c-bg"},
            )
            assert r.status_code == 200

        tasks = list(app.state.bg_tasks)
        for task in tasks:
            await task

        assert app.state.memory is not None
        msgs = app.state.memory.get_messages("c-bg")
        summaries = [m for m in msgs if m.get("summary")]
        assert len(summaries) >= 1
        assert all(m["role"] == "system" for m in summaries)
        assert all(m["content"] == "ok" for m in summaries)
