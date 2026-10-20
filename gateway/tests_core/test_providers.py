import pytest
from unittest.mock import Mock, patch

from app.config import Settings
from app.providers import build_llm
from app.providers.llm_base import LLMProvider, ProviderCapabilities, ReplyParseError
from app.providers.llm_gemini import GeminiLLMProvider
from app.providers.llm_ollama import OllamaLLMProvider
from app.providers.llm_llamacpp import LlamaCppLLMProvider


def _ollama_settings(**kw):
    base = dict(ai_provider="ollama", ollama_model="test-model")
    base.update(kw)
    return Settings(**base)


def _llamacpp_settings(**kw):
    base = dict(ai_provider="llamacpp", llamacpp_base_url="http://ai-max:8080/v1",
                llamacpp_model="test-llm")
    base.update(kw)
    return Settings(**base)


def test_build_llm_gemini() -> None:
    settings = Settings(ai_provider="gemini", gemini_api_key="test-key",
                        gemini_model="gemini-test")
    with patch("app.providers.llm_gemini.GeminiLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        assert build_llm(settings) is mock_provider
        mock_class.assert_called_once_with(settings)


def test_build_llm_ollama() -> None:
    settings = _ollama_settings()
    with patch("app.providers.llm_ollama.OllamaLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        assert build_llm(settings) is mock_provider


def test_build_llm_llamacpp() -> None:
    settings = _llamacpp_settings()
    with patch("app.providers.llm_llamacpp.LlamaCppLLMProvider") as mock_class:
        mock_provider = Mock()
        mock_class.return_value = mock_provider
        assert build_llm(settings) is mock_provider


def test_legacy_openai_compat_alias_maps_to_llamacpp() -> None:
    settings = _llamacpp_settings(ai_provider="openai_compat")
    assert settings.ai_provider == "llamacpp"


def test_build_llm_incomplete_gemini_returns_none() -> None:
    settings = Settings(ai_provider="gemini")
    assert build_llm(settings) is None  # no API key -> honest disabled, no raise


def test_build_llm_unknown_provider() -> None:
    settings = Settings(ai_provider="ollama", ollama_model="m")
    with pytest.raises(ValueError, match="Unknown AI provider"):
        build_llm(settings, provider="totally-bogus")


def test_parse_llm_reply_valid_json() -> None:
    raw = '{"spoken_text": "Hello", "emotion": "happy"}'
    result = GeminiLLMProvider.parse_llm_reply(raw)
    assert result["spoken_text"] == "Hello"
    assert result["emotion"] == "happy"


def test_parse_llm_reply_json_in_text() -> None:
    raw = 'Here: ```json{"spoken_text": "Hello", "emotion": "happy"}'''
    result = GeminiLLMProvider.parse_llm_reply(raw)
    assert result["spoken_text"] == "Hello"


def test_parse_llm_reply_plain_text_bounded_fallback() -> None:
    raw = "I would love to help with that!"
    result = LLMProvider.parse_llm_reply(raw)
    assert result["spoken_text"] == "I would love to help with that!"
    assert result["emotion"] == "neutral"


def test_normalize_structured_invalid_fields_clamped() -> None:
    data = {"spoken_text": "hi", "emotion": "rage", "expression_intensity": 9.0,
            "animation_hint": "x" * 40, "action": "rm -rf"}
    out = LLMProvider.normalize_structured(data)
    assert out["emotion"] == "neutral"
    assert out["expression_intensity"] == 1.0
    assert len(out["animation_hint"]) <= 10
    assert out["action"] == "none"


def test_normalize_structured_no_text_raises() -> None:
    with pytest.raises(ReplyParseError):
        LLMProvider.normalize_structured({"emotion": "happy"})


def test_normalize_tool_calls_bounded() -> None:
    calls = [{"name": f"t{i}", "arguments": {}} for i in range(9)]
    out = LLMProvider.normalize_structured({"spoken_text": "x", "tool_calls": calls})
    assert len(out["tool_calls"]) == 4


def test_capabilities_differ_per_provider() -> None:
    o = OllamaLLMProvider(_ollama_settings())
    l = LlamaCppLLMProvider(_llamacpp_settings())
    assert isinstance(o.capabilities(), ProviderCapabilities)
    assert o.name == "ollama" and l.name == "llamacpp"
    assert o.capabilities().list_models and l.capabilities().list_models
    assert o.tool_call_support() is True


def test_llamacpp_base_url_never_doubles_v1() -> None:
    a = LlamaCppLLMProvider(_llamacpp_settings(llamacpp_base_url="http://h:8080/v1"))
    b = LlamaCppLLMProvider(_llamacpp_settings(llamacpp_base_url="http://h:8080"))
    assert a.api_root == "http://h:8080/v1"
    assert b.api_root == "http://h:8080/v1"
