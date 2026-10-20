"""Ollama adapter using the NATIVE HTTP API (/api/chat, /api/tags, /api/version).

Never assumes Ollama runs on the gateway host: the base URL is fully
configured (IPv4/IPv6/hostname/FQDN/HTTPS). Native and OpenAI-compatible paths
are never mixed - this file only speaks the native Ollama dialect.
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


class OllamaLLMProvider(LLMProvider):
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        if not settings.ollama_base_url:
            raise ValueError("OLLAMA_BASE_URL required for ollama provider")
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = (settings.ollama_model or "").strip()
        if not self.model:
            raise ValueError("OLLAMA_MODEL required for ollama provider")
        self.timeout = settings.timeout_for("ollama")
        self.auth_mode = settings.ollama_auth_mode
        self._api_key = settings.ollama_api_key.get_secret_value()
        if self.auth_mode == "bearer" and not self._api_key:
            raise ValueError("ollama auth_mode=bearer but OLLAMA_API_KEY is empty")
        self.verify = settings.tls_verify_outbound

    # ---- helpers ------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        if self.auth_mode == "bearer" and self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, verify=self.verify, headers=self._headers())

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="ollama", model=self.model,
            json_schema=False,   # enforced via format="json" + bounded parser
            native_tool_calling=True, streaming=True, list_models=True,
            notes="native /api/chat; structured output via json format flag",
        )

    @staticmethod
    def _to_ollama_messages(
        messages: List[Dict[str, Any]], system_prompt: Optional[str],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
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
            "messages": self._to_ollama_messages(messages, system_prompt),
            "stream": stream,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
            },
        }
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
        return body

    @staticmethod
    def _merge_tool_calls(msg: Dict[str, Any], reply: Dict[str, Any]) -> Dict[str, Any]:
        calls = msg.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            return reply
        norm = []
        for call in calls[:4]:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") or call
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

    # ---- contract ------------------------------------------------------------
    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = self._chat_body(messages, system_prompt, tools, stream=False)
        body["format"] = "json"
        async with self._client(self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        msg = data.get("message") or {}
        content = str(msg.get("content") or "").strip()
        if not content and not msg.get("tool_calls"):
            raise ReplyParseError("ollama returned an empty reply")
        if content:
            reply = self.parse_llm_reply(content)
        else:
            # Tool-call-only turn: empty speech is legitimate, never fake text.
            reply = {"spoken_text": "", "emotion": "thinking",
                     "expression_intensity": 1.0, "animation_hint": "none",
                     "action": "none"}
        reply = self._merge_tool_calls(msg, reply)
        if not str(reply.get("spoken_text") or "").strip() and not reply.get("tool_calls"):
            raise ReplyParseError("ollama reply had neither text nor tool calls")
        return reply

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = self._chat_body(messages, system_prompt, None, stream=False)
        # Ollama structured-output: pass the JSON schema itself as format.
        body["format"] = schema
        async with self._client(self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=body)
            if resp.status_code >= 400:
                # Older Ollama builds reject schema-format: bounded retry plain.
                logger.warning("ollama schema format rejected (%s), plain json retry",
                               resp.status_code)
                return await self.generate_reply(messages, tools=None,
                                                 system_prompt=system_prompt)
            resp.raise_for_status()
            data = resp.json()
        content = str((data.get("message") or {}).get("content") or "")
        return self.parse_llm_reply(content)

    async def stream_reply(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        body = self._chat_body(messages, system_prompt, None, stream=True)
        body["format"] = "json"
        timeout = max(timeout_s, self.timeout)
        async with self._client(timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = str((chunk.get("message") or {}).get("content") or "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break

    async def list_models(self, timeout_s: float = 10.0) -> List[str]:
        async with self._client(min(timeout_s, 15.0)) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        return [str(m.get("name", "")) for m in data.get("models", []) if m.get("name")]

    async def health(self, timeout_s: float = 5.0) -> bool:
        try:
            async with self._client(min(timeout_s, 15.0)) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                ok = resp.status_code == 200
                data = resp.json() if ok else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ollama health check failed: %s", exc)
            return False
        logger.info("ollama %s reachable at %s", data.get("version", "?"), self.base_url)
        if ok and self.settings.validate_model_ids and self.model:
            try:
                known = any(self.model == m or self.model in m or m in self.model
                            for m in await self.list_models(timeout_s=timeout_s))
            except Exception:  # noqa: BLE001
                known = True  # model list unavailable: don't punish health
            if not known:
                logger.error("ollama model %r not present in /api/tags", self.model)
                return False
        return ok
