"""Gemini adapter against a stubbed google-genai SDK (works without network)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from app.config import Settings
from app.providers import llm_gemini
from app.providers.llm_base import ReplyParseError


class FakeTypes:
    class Content:
        def __init__(self, role: str = "", parts: Any = None, **kw):
            self.role, self.parts = role, parts

    class Part:
        def __init__(self, text: str = "", **kw):
            self.text = text

        @classmethod
        def from_text(cls, text: str = "", **kw):
            return cls(text=text)

    class FunctionDeclaration:
        def __init__(self, name: str = "", description: str = "", parameters: Any = None):
            self.name, self.description, self.parameters = name, description, parameters

    class Tool:
        def __init__(self, function_declarations: Any = None):
            self.function_declarations = function_declarations or []

    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kwargs = kw


REPLY = ('{"spoken_text": "Hi from Gemini", "emotion": "happy",'
         ' "expression_intensity": 0.9, "animation_hint": "none", "action": "none"}')


class FakeModels:
    def __init__(self, provider: Any):
        self._p = provider

    async def generate_content(self, model: str, contents: Any, config: Any):
        self._p.calls.append({"model": model, "config": config})
        return self._p.next_response()

    async def generate_content_stream(self, model: str, contents: Any, config: Any):
        pieces = self._p.stream_pieces

        async def _iter():
            for piece in pieces:
                yield SimpleNamespace(text=piece)
        return _iter()

    def list(self):  # sync pager used via asyncio.to_thread
        return [SimpleNamespace(name="models/gemini-2.5-flash")]


def make_provider(monkeypatch, *, text: str = "", function_calls: Any = None,
                  stream: List[str] | None = None) -> Any:
    monkeypatch.setattr(llm_gemini, "genai_types", FakeTypes)
    monkeypatch.setattr(llm_gemini, "genai", SimpleNamespace(Client=object))
    settings = Settings(ai_provider="gemini", gemini_api_key="gk",
                        gemini_model="gemini-2.5-flash")
    prov = llm_gemini.GeminiLLMProvider(settings)

    def _next():
        if function_calls:
            part = SimpleNamespace(text="", function_call=None)
            parts = []
            for fc in function_calls:
                parts.append(SimpleNamespace(
                    text="", function_call=SimpleNamespace(name=fc["name"], args=fc["args"])))
            cand = SimpleNamespace(content=SimpleNamespace(parts=parts))
        else:
            cand = SimpleNamespace(content=SimpleNamespace(
                parts=[SimpleNamespace(text=text)]))
        return SimpleNamespace(text=text, candidates=[cand])

    prov.next_response = _next
    prov.stream_pieces = stream or []
    prov.calls = []
    models = FakeModels(prov)
    prov._client = SimpleNamespace(
        aio=SimpleNamespace(models=models), models=models)
    return prov


MESSAGES = [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_gemini_generate_reply_parses_text(monkeypatch) -> None:
    prov = make_provider(monkeypatch, text=REPLY)
    reply = await prov.generate_reply(MESSAGES, system_prompt="sys")
    assert reply["spoken_text"] == "Hi from Gemini"
    assert prov.calls[0]["model"] == "gemini-2.5-flash"
    assert prov.calls[0]["config"].kwargs["response_mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_gemini_function_calls_become_tool_calls(monkeypatch) -> None:
    prov = make_provider(monkeypatch, text="", function_calls=[
        {"name": "get_weather", "args": {"city": "Bangkok"}}])
    reply = await prov.generate_reply(MESSAGES, tools=[
        {"name": "get_weather", "description": "d", "parameters": {}}])
    assert reply["tool_calls"] == [{"name": "get_weather",
                                    "arguments": {"city": "Bangkok"}}]
    assert reply["spoken_text"] == ""


@pytest.mark.asyncio
async def test_gemini_empty_reply_raises(monkeypatch) -> None:
    prov = make_provider(monkeypatch, text="")
    with pytest.raises(ReplyParseError):
        await prov.generate_reply(MESSAGES)


@pytest.mark.asyncio
async def test_gemini_stream(monkeypatch) -> None:
    prov = make_provider(monkeypatch, stream=["Hel", "lo"])
    out = ""
    async for piece in prov.stream_reply(MESSAGES):
        out += piece
    assert out == "Hello"


@pytest.mark.asyncio
async def test_gemini_list_models_strips_prefix(monkeypatch) -> None:
    prov = make_provider(monkeypatch)
    assert await prov.list_models() == ["gemini-2.5-flash"]


@pytest.mark.asyncio
async def test_gemini_health_validates_model(monkeypatch) -> None:
    prov = make_provider(monkeypatch)
    assert await prov.health() is True


def test_gemini_requires_key_without_stub(monkeypatch) -> None:
    settings = Settings(ai_provider="gemini")
    with pytest.raises(ValueError):
        llm_gemini.GeminiLLMProvider(settings)
