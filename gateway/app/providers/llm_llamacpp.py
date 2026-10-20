"""llama.cpp server adapter via its OpenAI-compatible API.

Base URL handling: config may give http://host:8080/v1 or http://host:8080;
paths resolve to {root}/models and {root}/chat/completions without ever
appending /v1 twice. Auth: none (no header, no dummy key) or bearer token
(behind llama-server --api-key or a reverse proxy). Streaming: SSE chunks.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import Settings
from app.providers.llm_base import (
    LLMProvider,
    ProviderCapabilities,
    ReplyParseError,
)

logger = logging.getLogger(__name__)


class LlamaCppLLMProvider(LLMProvider):
    name = "llamacpp"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        if not settings.llamacpp_base_url:
            raise ValueError("LLAMACPP_BASE_URL required for llamacpp provider")
        base = settings.llamacpp_base_url.rstrip("/")
        self.api_root = base if base.endswith("/v1") else f"{base}/v1"
        self.model = (settings.llamacpp_model or "").strip()
        self.timeout = settings.timeout_for("llamacpp")
        self.auth_mode = settings.llamacpp_auth_mode
        self._api_key = settings.llamacpp_api_key.get_secret_value()
        if self.auth_mode == "bearer" and not self._api_key:
            raise ValueError("llamacpp auth_mode=bearer but LLAMACPP_API_KEY is empty")
        self.verify = settings.tls_verify_outbound

    def _headers(self) -> Dict[str, str]:
        if self.auth_mode == "bearer" and self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, verify=self.verify, headers=self._headers())

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="llamacpp", model=self.model,
            json_schema=True,        # response_format json_object
            native_tool_calling=True, streaming=True, list_models=True,
            notes="OpenAI-compatible llama-server; json/streams depend on build",
        )

    @staticmethod
    def _to_chat_messages(
        messages: List[Dict[str, Any]], system_prompt: Optional[str],
    ) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        for msg in messages:
            role = str(msg.get("role") or "user")
            if role not in ("user", "assistant", "system"):
                role = "user"
            out.append({"role": role, "content": str(msg.get("content", ""))})
        return out

    def _chat_body(
        self, messages: List[Dict[str, Any]], system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]], stream: bool = False,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_chat_messages(messages, system_prompt),
            "temperature": self.settings.llamacpp_temperature,
            "stream": stream,
        }
        if not stream:
            body["response_format"] = {"type": "json_object"}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"
        return body

    @staticmethod
    def _normalize_openai_tools(content: str, msg: Dict[str, Any]) -> Dict[str, Any]:
        reply: Dict[str, Any]
        if content.strip():
            reply = LLMProvider.parse_llm_reply(content)
        else:
            reply = {"spoken_text": "", "emotion": "thinking",
                     "expression_intensity": 1.0, "animation_hint": "none",
                     "action": "none"}
        calls = msg.get("tool_calls")
        if isinstance(calls, list):
            norm = []
            for call in calls[:4]:
                fn = call.get("function") or {}
                cname = str(fn.get("name") or "").strip()
                if not cname:
                    continue
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                norm.append({"name": cname, "arguments": args})
            if norm:
                reply["tool_calls"] = norm
        return reply

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = self._chat_body(messages, system_prompt, tools, stream=False)
        async with self._client(self.timeout) as client:
            resp = await client.post(f"{self.api_root}/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ReplyParseError("llamacpp response contained no choices")
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "")
        reply = self._normalize_openai_tools(content, msg)
        if not str(reply.get("spoken_text") or "").strip() and not reply.get("tool_calls"):
            raise ReplyParseError("llamacpp reply had neither text nor tool calls")
        return reply

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = self._chat_body(messages, system_prompt, None, stream=False)
        # llama-server accepts json_schema response_format in recent builds;
        # fall back to plain json_object on older ones (bounded retry).
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "aura_reply", "schema": schema, "strict": False,
        }}
        try:
            async with self._client(self.timeout) as client:
                resp = await client.post(f"{self.api_root}/chat/completions", json=body)
                if resp.status_code >= 400:
                    raise ReplyParseError(f"json_schema rejected ({resp.status_code})")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("llamacpp json_schema rejected (%s), plain json retry",
                           exc.response.status_code)
            return await self.generate_reply(messages, system_prompt=system_prompt)
        except ReplyParseError:
            logger.warning("llamacpp json_schema rejected, plain json retry")
            return await self.generate_reply(messages, system_prompt=system_prompt)
        choices = data.get("choices") or []
        if not choices:
            raise ReplyParseError("llamacpp response contained no choices")
        content = str((choices[0].get("message") or {}).get("content") or "")
        return self.parse_llm_reply(content)

    async def stream_reply(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        body = self._chat_body(messages, system_prompt, None, stream=True)
        body.pop("response_format", None)
        timeout = max(timeout_s, self.timeout)
        async with self._client(timeout) as client:
            async with client.stream(
                "POST", f"{self.api_root}/chat/completions", json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = str(delta.get("content") or "")
                    if piece:
                        yield piece

    async def list_models(self, timeout_s: float = 10.0) -> List[str]:
        async with self._client(min(timeout_s, 15.0)) as client:
            resp = await client.get(f"{self.api_root}/models")
            resp.raise_for_status()
            data = resp.json()
        out: List[str] = []
        for item in data.get("data", []):
            mid = str(item.get("id", "")).strip()
            if mid:
                out.append(mid)
        return out

    async def health(self, timeout_s: float = 5.0) -> bool:
        try:
            models = await self.list_models(timeout_s=timeout_s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("llamacpp health check failed: %s", exc)
            return False
        if self.settings.validate_model_ids and self.model:
            known = any(self.model == m or self.model in m or m in self.model
                        for m in models)
            if models and not known:
                logger.error("llamacpp model %r not present in %d listed models",
                             self.model, len(models))
                return False
        return True
