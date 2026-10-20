"""Gemini adapter using the maintained google-genai SDK (optional extra).

Cloud provider: selected explicitly or via failover only when
allow_cloud_failover=true. Supports ordinary chat, structured (response
schema) replies and native function calling; capabilities reflect what this
adapter actually implements, and missing SDK features degrade to the bounded
shared parser instead of pretending.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import Settings
from app.providers.llm_base import (
    LLMProvider,
    ProviderCapabilities,
    ReplyParseError,
)

logger = logging.getLogger(__name__)

try:  # optional extra: uv sync --extras gemini
    import google.genai as genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - depends on extras install
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


def _part_text(part: Any) -> str:
    text = getattr(part, "text", None)
    return text if isinstance(text, str) else ""


def _function_calls_from(resp: Any) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    try:
        candidates = resp.candidates or []
    except Exception:  # noqa: BLE001
        return calls
    for cand in candidates:
        try:
            parts = (cand.content.parts or []) if cand.content else []
        except Exception:  # noqa: BLE001
            continue
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is None:
                continue
            try:
                args = fc.args
                if not isinstance(args, dict):
                    args = dict(args) if args else {}
            except Exception:  # noqa: BLE001
                args = {}
            name = str(getattr(fc, "name", "") or "").strip()
            if name:
                calls.append({"name": name, "arguments": args})
    return calls


class GeminiLLMProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.model = (settings.gemini_model or "gemini-2.5-flash").strip()
        self.api_key = settings.gemini_api_key.get_secret_value()
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY required for gemini provider")
        self.timeout = settings.timeout_for("gemini")
        self.base_url = settings.gemini_base_url
        self._client = None

    def _get_client(self):
        if genai is None:
            raise RuntimeError("google-genai not installed (uv sync --extras gemini)")
        if self._client is None:
            if self.base_url:
                opts_cls = getattr(genai_types, "ClientOptions", None) if genai_types else None
                if opts_cls is not None:
                    self._client = genai.Client(api_key=self.api_key,
                                                client_options=opts_cls(base_url=self.base_url))
                else:
                    self._client = genai.Client(api_key=self.api_key, base_url=self.base_url)
            else:
                self._client = genai.Client(api_key=self.api_key)
        return self._client

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="gemini", model=self.model,
            json_schema=True, native_tool_calling=True, streaming=True,
            list_models=True,
            thinking_modes="-thinking" in self.model or "2.5" in self.model,
            notes="google-genai SDK; structured via response schema",
        )

    @staticmethod
    def _to_contents(messages: List[Dict[str, Any]]) -> List[Any]:
        out = []
        for msg in messages:
            role = str(msg.get("role") or "user")
            role = "user" if role == "user" else "model"
            out.append(genai_types.Content(
                role=role, parts=[genai_types.Part.from_text(text=str(msg.get("content", "")))]
            ))
        return out

    def _build_config(
        self,
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        schema: Optional[Dict[str, Any]] = None,
    ):
        kwargs: Dict[str, Any] = {
            "temperature": self.settings.gemini_temperature,
            "top_p": self.settings.gemini_top_p,
            "candidate_count": 1,
            "response_mime_type": "application/json",
        }
        if schema is not None:
            kwargs["response_schema"] = schema
        if system_prompt:
            kwargs["system_instruction"] = system_prompt
        if tools:
            declarations = []
            for tool in tools:
                params = tool.get("parameters") or {"type": "OBJECT", "properties": {}}
                declarations.append(genai_types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=params,
                ))
            kwargs["tools"] = [genai_types.Tool(function_declarations=declarations)]
        return genai_types.GenerateContentConfig(**kwargs)

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self.model,
                contents=self._to_contents(messages),
                config=self._build_config(system_prompt, tools),
            ),
            timeout=self.timeout,
        )
        text = ""
        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001 - text absent on function-call-only turns
            pass
        calls = _function_calls_from(resp)
        if not text.strip():
            if calls:
                reply: Dict[str, Any] = {"spoken_text": "", "emotion": "thinking",
                                         "expression_intensity": 1.0,
                                         "animation_hint": "none", "action": "none"}
            else:
                raise ReplyParseError("Gemini returned an empty reply")
        else:
            reply = self.parse_llm_reply(text)
        if calls:
            reply["tool_calls"] = calls[:4]
        return reply

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self.model,
                contents=self._to_contents(messages),
                config=self._build_config(system_prompt, None, schema=schema),
            ),
            timeout=self.timeout,
        )
        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001
            text = ""
        if not text.strip():
            raise ReplyParseError("Gemini structured reply was empty")
        return self.parse_llm_reply(text)

    async def stream_reply(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        stream = await client.aio.models.generate_content_stream(
            model=self.model,
            contents=self._to_contents(messages),
            config=self._build_config(system_prompt, None),
        )
        async for chunk in stream:
            piece = ""
            try:
                piece = chunk.text or ""
            except Exception:  # noqa: BLE001
                continue
            if piece:
                yield piece

    async def list_models(self, timeout_s: float = 10.0) -> List[str]:
        client = self._get_client()

        def _list() -> List[str]:
            return [m.name or "" for m in client.models.list() if getattr(m, "name", None)]

        names = await asyncio.wait_for(asyncio.to_thread(_list), timeout=timeout_s)
        prefix = "models/"
        return [n[len(prefix):] if n.startswith(prefix) else n for n in names if n]

    async def health(self, timeout_s: float = 5.0) -> bool:
        if genai is None or not self.api_key:
            return False
        try:
            models = await self.list_models(timeout_s=timeout_s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gemini health check failed: %s", exc)
            return False
        if self.settings.validate_model_ids and models:
            known = any(self.model == m or self.model in m or m in self.model
                        for m in models)
            if not known:
                logger.error("gemini model %r not in provider model list", self.model)
                return False
        return True
