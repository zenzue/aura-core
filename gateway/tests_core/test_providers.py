import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.config import Settings
from app.providers import build_llm
from app.providers.llm_base import ReplyParseError
from app.providers.llm_gemini import GeminiLLMProvider
from app.providers.llm_ollama import OllamaLLMProvider
from app.providers.llm_openai_compat import OpenAICompatLLMProvider


@pytest.mark.asyncio
async def test_build_llm_gemini() -> None:
    """Test building Gemini provider."""
    settings = Settings(
        ai_provider="gemini",
        gemini_api_key="test-key",
        gemini_model="gemini-test",
    )
    
    with patch("app.providers.llm_gemini.GeminiLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        
        result = build_llm(settings)
        assert result == mock_provider
        mock_class.assert_called_once_with(settings)


@pytest.mark.asyncio
async def test_build_llm_ollama() -> None:
    """Test building Ollama provider."""
    settings = Settings(ai_provider="ollama", ollama_model="llama-test")
    
    with patch("app.providers.llm_ollama.OllamaLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        
        result = build_llm(settings)
        assert result == mock_provider
        mock_class.assert_called_once_with(settings)


@pytest.mark.asyncio
async def test_build_llm_openai() -> None:
    """Test building OpenAI provider."""
    settings = Settings(
        ai_provider="openai_compat",
        openai_api_key="test-key",
        openai_model="gpt-test",
    )
    
    with patch("app.providers.llm_openai_compat.OpenAICompatLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        
        result = build_llm(settings)
        assert result == mock_provider
        mock_class.assert_called_once_with(settings)


@pytest.mark.asyncio
async def test_build_llm_unknown_provider() -> None:
    """Test building unknown provider."""
    settings = Settings(ai_provider="unknown")
    
    with pytest.raises(ValueError, match="Unknown AI provider: unknown"):
        build_llm(settings)


@pytest.mark.asyncio
async def test_parse_llm_reply_valid_json() -> None:
    """Test parsing valid JSON reply."""
    raw = '{"spoken_text": "Hello", "emotion": "happy"}'
    result = GeminiLLMProvider.parse_llm_reply(raw)
    assert result == {"spoken_text": "Hello", "emotion": "happy"}


@pytest.mark.asyncio
async def test_parse_llm_reply_json_in_text() -> None:
    """Test parsing JSON embedded in text."""
    raw = 'Here is the response: ```json{"spoken_text": "Hello", "emotion": "happy"}```'
    result = GeminiLLMProvider.parse_llm_reply(raw)
    assert result == {"spoken_text": "Hello", "emotion": "happy"}


@pytest.mark.asyncio
async def test_parse_llm_reply_malformed() -> None:
    """Test parsing malformed reply."""
    with pytest.raises(ReplyParseError):
        GeminiLLMProvider.parse_llm_reply("malformed json")


@pytest.mark.asyncio
async def test_ollama_health() -> None:
    """Test Ollama health check."""
    settings = Settings()
    provider = OllamaLLMProvider(settings)
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await provider.health()
        assert result is True


@pytest.mark.asyncio
async def test_openai_health() -> None:
    """Test OpenAI health check."""
    settings = Settings(ai_provider="openai_compat", openai_compat_api_key="test-key")
    provider = OpenAICompatLLMProvider(settings)
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await provider.health()
        assert result is True