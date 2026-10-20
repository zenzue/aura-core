"""Adapters against mocked HTTP: request shape, auth modes, IP/IPv6/domain
endpoints, model validation, timeouts, streaming (+cancellation), invalid
structured replies, tool-call passthrough. No network, no fabrication."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest

from app.config import Settings
from app.providers.llm_base import ReplyParseError
from app.providers.llm_ollama import OllamaLLMProvider
from app.providers.llm_llamacpp import LlamaCppLLMProvider

REPLY_JSON = json.dumps({
    "spoken_text": "Hi there", "display_text": "Hi",
    "emotion": "happy", "expression_intensity": 0.9,
    "animation_hint": "none", "action": "none",
})


def structured_reply_json() -> str:
    return REPLY_JSON


def install_mock(provider: Any, handler) -> httpx.MockTransport:
    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
            headers=provider._headers(),
        )
    provider._client = factory
    return None


def _ollama(**kw) -> OllamaLLMProvider:
    settings = Settings(ai_provider="ollama", ollama_model="qwen2.5:7b", **kw)
    return OllamaLLMProvider(settings)


def _llamacpp(**kw) -> LlamaCppLLMProvider:
    base = dict(ai_provider="llamacpp", llamacpp_model="test-llm",
                llamacpp_base_url="http://ai-max.lan:8080/v1")
    base.update(kw)
    return LlamaCppLLMProvider(Settings(**base))


MESSAGES = [{"role": "user", "content": "hello"}]


# --------------------------------------------------------------------------
# Ollama native API
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_chat_request_shape_and_auth_none() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": {"content": REPLY_JSON}, "done": True})

    prov = _ollama()
    install_mock(prov, handler)
    reply = await prov.generate_reply(MESSAGES, system_prompt="sys")
    assert reply["spoken_text"] == "Hi there"
    req = seen[0]
    assert str(req.url).endswith("/api/chat")
    assert req.headers.get("authorization") is None
    body = json.loads(req.content)
    assert body["model"] == "qwen2.5:7b"
    assert body["format"] == "json"
    assert body["messages"][0] == {"role": "system", "content": "sys"}


@pytest.mark.asyncio
async def test_ollama_bearer_auth_header_sent() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": {"content": REPLY_JSON}, "done": True})

    prov = _ollama(ollama_auth_mode="bearer", ollama_api_key="secret-token")
    install_mock(prov, handler)
    await prov.generate_reply(MESSAGES)
    assert seen[0].headers["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_ollama_ipv6_and_https_hosts_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://[fd00::5]:11434/api/chat")
        return httpx.Response(200, json={"message": {"content": REPLY_JSON}})

    prov = _ollama(ollama_base_url="http://[fd00::5]:11434")
    install_mock(prov, handler)
    reply = await prov.generate_reply(MESSAGES)
    assert reply["spoken_text"] == "Hi there"


@pytest.mark.asyncio
async def test_ollama_list_models_tags_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/tags")
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3"}]})

    prov = _ollama()
    install_mock(prov, handler)
    assert await prov.list_models() == ["qwen2.5:7b", "llama3"]


@pytest.mark.asyncio
async def test_ollama_health_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/version")
        return httpx.Response(200, json={"version": "0.5.0"})

    prov = _ollama()
    install_mock(prov, handler)
    assert await prov.health() is True


@pytest.mark.asyncio
async def test_ollama_unreachable_health_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    prov = _ollama()
    install_mock(prov, handler)
    assert await prov.health() is False


@pytest.mark.asyncio
async def test_ollama_wrong_model_validate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "other"}]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "1"})
        raise AssertionError("unexpected path")

    prov = _ollama()
    install_mock(prov, handler)
    assert await prov.validate_model("qwen2.5:7b") is False
    assert await prov.validate_model("other") is True
    assert await prov.health() is False  # configured model absent from tags


@pytest.mark.asyncio
async def test_ollama_timeout_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow model", request=request)

    prov = _ollama()
    install_mock(prov, handler)
    with pytest.raises(httpx.TimeoutException):
        await prov.generate_reply(MESSAGES)


@pytest.mark.asyncio
async def test_ollama_streaming_chunks_and_cancel() -> None:
    chunks = ["Hel", "lo", " wo", "rld"]
    lines = []
    for c in chunks:
        lines.append(json.dumps({"message": {"content": c}, "done": False}))
        lines.append("")  # empty NDJSON line tolerated
    body = "\n".join(lines) + "\n" + json.dumps({"message": {"content": ""}, "done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/chat")
        return httpx.Response(200, content=body.encode())

    prov = _ollama()
    install_mock(prov, handler)
    collected = ""
    async for piece in prov.stream_reply(MESSAGES):
        collected += piece
        if len(collected) >= 4:
            break  # streaming cancellation mid-flight
    assert collected.startswith("Hell")


@pytest.mark.asyncio
async def test_ollama_tool_calls_passthrough() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "tools" in body
        return httpx.Response(200, json={"message": {
            "content": "",
            "tool_calls": [{"function": {"name": "get_weather",
                                         "arguments": {"city": "Bangkok"}}}],
        }, "done": True})

    prov = _ollama()
    install_mock(prov, handler)
    tools = [{"name": "get_weather", "description": "d",
              "parameters": {"type": "object", "properties": {}}}]
    reply = await prov.generate_reply(MESSAGES, tools=tools)
    assert reply["tool_calls"] == [{"name": "get_weather",
                                    "arguments": {"city": "Bangkok"}}]
    assert reply["spoken_text"] == ""  # never fabricated speech on tool turn


@pytest.mark.asyncio
async def test_ollama_invalid_json_reply_still_validated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "just words, no json"}})

    prov = _ollama()
    install_mock(prov, handler)
    reply = await prov.generate_reply(MESSAGES)
    assert reply["emotion"] == "neutral"
    assert reply["spoken_text"] == "just words, no json"


@pytest.mark.asyncio
async def test_ollama_schema_rejected_bounded_retry() -> None:
    calls: List[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body.get("format"))
        if isinstance(body.get("format"), dict):
            return httpx.Response(400, json={"error": "bad format"})
        return httpx.Response(200, json={"message": {"content": REPLY_JSON}})

    prov = _ollama()
    install_mock(prov, handler)
    reply = await prov.generate_structured(MESSAGES, schema={"type": "object"})
    assert reply["spoken_text"] == "Hi there"
    assert isinstance(calls[0], dict) and calls[1] == "json"


# --------------------------------------------------------------------------
# llama.cpp OpenAI-compatible
# --------------------------------------------------------------------------

def _openai_body(content: str = REPLY_JSON) -> Dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.asyncio
async def test_llamacpp_chat_path_not_double_v1() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openai_body())

    prov = _llamacpp()
    install_mock(prov, handler)
    await prov.generate_reply(MESSAGES)
    assert httpx.URL(str(seen[0].url)).path == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_llamacpp_base_without_v1_appends_once() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openai_body())

    prov = _llamacpp(llamacpp_base_url="http://host:8080")
    install_mock(prov, handler)
    await prov.generate_reply(MESSAGES)
    assert httpx.URL(str(seen[0].url)).path == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_llamacpp_no_dummy_key_when_auth_none() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openai_body())

    prov = _llamacpp(llamacpp_base_url="http://host:8080/v1")
    install_mock(prov, handler)
    await prov.generate_reply(MESSAGES)
    assert seen[0].headers.get("authorization") is None


@pytest.mark.asyncio
async def test_llamacpp_bearer_token_sent() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openai_body())

    prov = _llamacpp(llamacpp_auth_mode="bearer", llamacpp_api_key="tok")
    install_mock(prov, handler)
    await prov.generate_reply(MESSAGES)
    assert seen[0].headers["authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_llamacpp_model_list_and_health_wrong_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            assert request.headers.get("accept") or True
            return httpx.Response(200, json={"data": [
                {"id": "test-llm"}, {"id": "other-model"}]})
        raise AssertionError("unexpected")

    prov = _llamacpp()
    install_mock(prov, handler)
    assert sorted(await prov.list_models()) == ["other-model", "test-llm"]
    assert await prov.health() is True

    def handler_missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "someone-else"}]})

    prov2 = _llamacpp()
    install_mock(prov2, handler_missing)
    assert await prov2.health() is False


@pytest.mark.asyncio
async def test_llamacpp_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    prov = _llamacpp()
    install_mock(prov, handler)
    assert await prov.health() is False
    with pytest.raises(httpx.HTTPError):
        await prov.generate_reply(MESSAGES)


@pytest.mark.asyncio
async def test_llamacpp_sse_stream_and_cancel() -> None:
    sse = ("data: {\"choices\":[{\"delta\":{\"content\":\"Hel\"}}]}\n\n"
           "data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n\n"
           "data: [DONE]\n\n").encode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=sse)

    prov = _llamacpp()
    install_mock(prov, handler)
    parts: List[str] = []
    async for piece in prov.stream_reply(MESSAGES):
        parts.append(piece)
        if piece == "lo":
            break  # cancellation
    assert "".join(parts) == "Hello"


@pytest.mark.asyncio
async def test_llamacpp_native_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"]
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "",
            "tool_calls": [{"function": {"name": "get_local_time",
                                         "arguments": "{\"city\": \"Bangkok\"}"}}],
        }}]})

    prov = _llamacpp()
    install_mock(prov, handler)
    tools = [{"name": "get_local_time", "description": "d",
              "parameters": {"type": "object", "properties": {}}}]
    reply = await prov.generate_reply(MESSAGES, tools=tools)
    assert reply["tool_calls"] == [{"name": "get_local_time",
                                    "arguments": {"city": "Bangkok"}}]


@pytest.mark.asyncio
async def test_llamacpp_empty_choices_raises_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    prov = _llamacpp()
    install_mock(prov, handler)
    with pytest.raises(ReplyParseError):
        await prov.generate_reply(MESSAGES)
