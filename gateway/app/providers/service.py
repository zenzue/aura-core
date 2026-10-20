"""ProviderService: unified AI access with bounded, opt-in failover.

Cloud failover is OFF unless allow_cloud_failover=true, so a failing local
provider never silently forwards private prompts to Gemini.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import Settings
from app.providers import build_llm
from app.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

CLOUD_PROVIDERS = {"gemini"}


class ProviderService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.active: Optional[LLMProvider] = None
        self.failover: List[LLMProvider] = []
        self.reload()

    # ---- construction / switching -------------------------------------------
    def reload(self) -> None:
        try:
            self.active = build_llm(self.settings)
        except ValueError as exc:
            logger.error("provider config invalid: %s", exc)
            self.active = None
        self.failover = []
        chain = [p.strip().lower() for p in self.settings.llm_failover_chain.split(",")
                 if p.strip()]
        for name in chain:
            if name == self.settings.ai_provider:
                continue
            if name in CLOUD_PROVIDERS and not self.settings.allow_cloud_failover:
                logger.warning("cloud failover target %r ignored (ALLOW_CLOUD_FAILOVER=false)", name)
                continue
            try:
                prov = build_llm(self.settings, provider=name)
            except ValueError as exc:
                logger.error("failover provider %r invalid: %s", name, exc)
                continue
            if prov is not None:
                self.failover.append(prov)

    def switch(self, provider: str) -> Dict[str, Any]:
        name = provider.strip().lower()
        try:
            prov = build_llm(self.settings, provider=name)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if prov is None:
            return {"ok": False, "error": "provider configuration incomplete"}
        self.settings.ai_provider = name
        self.reload()
        logger.info("active provider switched to %s", prov.name)
        return {"ok": True, "provider": prov.name, "model": prov.model}

    # ---- unified contract -----------------------------------------------------
    @property
    def name(self) -> str:
        return self.active.name if self.active else "disabled"

    @property
    def model(self) -> str:
        return self.active.model if self.active else ""

    def providers_order(self) -> List[LLMProvider]:
        out: List[LLMProvider] = []
        if self.active:
            out.append(self.active)
        out.extend(self.failover)
        return out

    async def ask(self, messages: List[Dict[str, Any]],
                  tools: Optional[List[Dict[str, Any]]] = None,
                  system_prompt: Optional[str] = None) -> Dict[str, Any]:
        providers = self.providers_order()
        if not providers:
            raise RuntimeError("no LLM provider configured")
        last: Optional[BaseException] = None
        for idx, prov in enumerate(providers):
            try:
                return await prov.generate_reply(messages, tools, system_prompt)
            except Exception as exc:  # noqa: BLE001
                last = exc
                logger.warning("provider %s failed (%s); attempts_left=%d",
                               prov.name, type(exc).__name__, len(providers) - idx - 1)
        raise last or RuntimeError("all providers failed")

    async def ask_structured(self, messages: List[Dict[str, Any]],
                             schema: Dict[str, Any],
                             system_prompt: Optional[str] = None) -> Dict[str, Any]:
        providers = self.providers_order()
        if not providers:
            raise RuntimeError("no LLM provider configured")
        last: Optional[BaseException] = None
        for prov in providers:
            try:
                return await prov.generate_structured(messages, schema, system_prompt)
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last or RuntimeError("all providers failed")

    def stream(self, messages: List[Dict[str, Any]],
               system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        prov = self.active
        if prov is None:
            raise RuntimeError("no LLM provider configured")

        async def _gen() -> AsyncIterator[str]:
            async for piece in prov.stream_reply(messages, system_prompt):
                yield piece

        return _gen()

    async def list_models(self, timeout_s: float = 10.0) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for prov in self.providers_order():
            try:
                out[prov.name] = await prov.list_models(timeout_s=timeout_s)
            except Exception as exc:  # noqa: BLE001
                out[prov.name] = f"error: {exc}"
        return out

    async def health(self, timeout_s: float = 5.0) -> bool:
        return bool((await self.check_health(timeout_s=timeout_s)).get("healthy"))

    async def check_health(self, timeout_s: float = 5.0) -> Dict[str, Any]:
        result: Dict[str, Any] = {"provider": self.name, "healthy": False}
        if self.active is None:
            result["reason"] = "no provider configured"
            if self.settings.problems():
                result["problems"] = list(self.settings.problems())
            return result
        try:
            result["healthy"] = bool(await self.active.health(timeout_s=timeout_s))
        except Exception as exc:  # noqa: BLE001
            result["reason"] = str(exc)
        result["model"] = self.model
        caps = self.active.capabilities()
        result["capabilities"] = {
            "json_schema": caps.json_schema,
            "native_tool_calling": caps.native_tool_calling,
            "streaming": caps.streaming,
            "list_models": caps.list_models,
            "thinking_modes": caps.thinking_modes,
        }
        if self.failover:
            result["failover"] = [p.name for p in self.failover]
        return result

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "failover_chain": [p.name for p in self.failover],
            "allow_cloud_failover": self.settings.allow_cloud_failover,
            "problems": list(self.settings.problems()),
        }

    async def generate_reply(self, messages: List[Dict[str, Any]],
                             tools: Optional[List[Dict[str, Any]]] = None,
                             system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """LLMProvider-protocol alias so memory/summarizer callers can use
        the service wherever a single provider object was expected."""
        return await self.ask(messages, tools=tools, system_prompt=system_prompt)
