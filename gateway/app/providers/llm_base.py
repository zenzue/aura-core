"""Unified AI provider contract shared by Gemini / Ollama / llama.cpp.

Every adapter must implement the same surface so the rest of the gateway never
knows which vendor answers. Capability flags declare what a given provider or
model can do; where a capability is missing callers must use the bounded
fallbacks implemented here instead of assuming support.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from app.config import EMOTIONS, Settings

MAX_SPKEN_LEN = 240  # hard cap for spoken_text length after normalization


class ReplyParseError(Exception):
    """LLM reply could not be parsed into the structured reply contract."""


@dataclass(frozen=True)
class ProviderCapabilities:
    """Explicit capability flags; detection per adapter/model.

    Never assume: native tool calling, JSON-schema constraint, thinking modes
    or identical streaming semantics across providers.
    """
    provider: str
    model: str = ""
    json_schema: bool = False          # can enforce our reply JSON schema
    native_tool_calling: bool = False  # provider-side function/tool calls
    streaming: bool = False
    list_models: bool = False
    thinking_modes: bool = False
    notes: str = ""


@dataclass
class ModelInfo:
    id: str
    provider: str
    size_mb: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Base class for LLM providers (unified contract)."""

    name: str = "unknown"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ---- core contract -------------------------------------------------------
    @abstractmethod
    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Structured emotional reply dict; raises on failure, never fakes."""

    @abstractmethod
    async def health(self, timeout_s: float = 5.0) -> bool:
        """Reachable/configured check."""

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    def tool_call_support(self) -> bool:
        return self.capabilities().native_tool_calling

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """JSON-schema-constrained generation where supported; adapters
        without schema support fall back to prompt-level JSON instruction and
        the shared bounded parser."""
        return await self.generate_reply(messages, tools=None, system_prompt=system_prompt)

    async def stream_reply(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        """Yield incremental text. Adapters without streaming yield once."""
        reply = await self.generate_reply(messages, system_prompt=system_prompt)
        text = reply.get("spoken_text") if isinstance(reply, dict) else None
        if isinstance(text, str) and text:
            yield text

    async def list_models(self, timeout_s: float = 10.0) -> List[str]:
        return []

    async def validate_model(self, model: str, timeout_s: float = 10.0) -> Optional[bool]:
        """True/False when a model list is available; None when unknown."""
        if not self.capabilities().list_models:
            return None
        try:
            models = await self.list_models(timeout_s=timeout_s)
        except Exception:  # noqa: BLE001
            return None
        if not models:
            return None
        return any(model == m or model in m or m in model for m in models)

    # ---- bounded structured validation ----------------------------------------
    @classmethod
    def normalize_structured(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce a parsed dict into the wire contract without inventing text.
        Emotion outside EMOTIONS -> neutral; intensity clamped; spoken kept."""
        if not isinstance(data, dict):
            raise ReplyParseError("structured reply is not an object")
        spoken = data.get("spoken_text") or data.get("display_text")
        if not isinstance(spoken, str) or not spoken.strip():
            raise ReplyParseError("structured reply has no speakable text")
        out: Dict[str, Any] = {"spoken_text": spoken.strip()[:MAX_SPKEN_LEN]}
        disp = data.get("display_text")
        if isinstance(disp, str) and disp.strip():
            out["display_text"] = disp.strip()[: MAX_SPKEN_LEN * 4]
        emo = str(data.get("emotion") or "neutral").strip().lower()
        out["emotion"] = emo if emo in EMOTIONS else "neutral"
        try:
            intensity = float(data.get("expression_intensity", 1.0))
        except (TypeError, ValueError):
            intensity = 1.0
        out["expression_intensity"] = max(0.5, min(1.0, intensity))
        hint = data.get("animation_hint")
        if isinstance(hint, str) and hint.strip():
            out["animation_hint"] = hint.strip().lower()[:10]
        action = str(data.get("action") or "none").strip().lower()
        out["action"] = action if action in {"none", "vibrate", "remember", "proactive"} else "none"
        calls = data.get("tool_calls")
        if isinstance(calls, list):
            norm: List[Dict[str, Any]] = []
            for call in calls[:4]:  # bounded: never trust a rambling model
                if not isinstance(call, dict):
                    continue
                cname = str(call.get("name") or "").strip()
                if not cname or len(cname) > 64:
                    continue
                args = call.get("arguments")
                if not isinstance(args, dict):
                    args = call.get("args") if isinstance(call.get("args"), dict) else {}
                norm.append({"name": cname, "arguments": args})
            if norm:
                out["tool_calls"] = norm
        return out

    @classmethod
    def parse_llm_reply(cls, raw: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Parse raw LLM response into a normalized dict. Raises ReplyParseError."""
        if isinstance(raw, dict):
            data: Optional[Dict[str, Any]] = raw
        elif isinstance(raw, str):
            data = None
            candidates = [raw.strip()]
            if "```" in raw:
                seg = raw.split("```json", 1)[-1] if "```json" in raw else raw.split("```", 1)[-1]
                seg = seg.split("```", 1)[0]
                candidates.append(seg.strip())
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                candidates.append(raw[start:end + 1])
            for cand in candidates:
                try:
                    parsed = json.loads(cand)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    data = parsed
                    break
            if data is None:
                # Plain sentence fallback: models love to ignore JSON rules.
                text = raw.strip()
                if not text:
                    raise ReplyParseError("empty LLM reply")
                return cls.normalize_structured({
                    "spoken_text": text[:MAX_SPKEN_LEN],
                    "emotion": "neutral",
                    "expression_intensity": 1.0,
                    "animation_hint": "none",
                    "action": "none",
                })
        else:
            raise ReplyParseError("LLM reply is neither dict nor str")
        return cls.normalize_structured(data)

    REPLY_JSON_SCHEMA: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "spoken_text": {
                "type": "string",
                "description": "Speakable text, <=240 characters",
                "maxLength": MAX_SPKEN_LEN,
            },
            "display_text": {
                "type": "string",
                "description": "Display text (optional, defaults to spoken_text)",
            },
            "emotion": {
                "type": "string",
                "enum": sorted(EMOTIONS),
                "description": "Emotion of the response",
            },
            "expression_intensity": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 1.0,
                "description": "Intensity of expression (0.5-1.0)",
            },
            "animation_hint": {
                "type": "string",
                "maxLength": 10,
                "description": "Short advisory token for animations",
            },
            "action": {
                "type": "string",
                "enum": ["none", "vibrate", "remember", "proactive"],
                "description": "Action to take after response",
            },
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["name", "arguments"],
                },
                "description": "Tool calls to execute",
            },
        },
        "required": ["spoken_text", "emotion", "expression_intensity", "animation_hint", "action"],
    }
