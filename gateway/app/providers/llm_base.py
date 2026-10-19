import json
from typing import Any, Dict, List, Optional, Union
from abc import ABC, abstractmethod

from app.config import Settings


class ReplyParseError(Exception):
    """Error when parsing LLM reply."""


class LLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a reply from the LLM."""
        pass

    @abstractmethod
    async def health(self, timeout_s: float = 5.0) -> bool:
        """Check if provider is healthy/reachable."""
        pass

    @classmethod
    def parse_llm_reply(cls, raw: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Parse raw LLM response into a normalized dict. Raises ReplyParseError."""
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise ReplyParseError("LLM reply is neither dict nor str")

        candidates = [raw.strip()]
        # strip ```json fences anywhere
        if "```" in raw:
            seg = raw.split("```json", 1)[-1] if "```json" in raw else raw.split("```", 1)[-1]
            seg = seg.split("```", 1)[0]
            candidates.append(seg.strip())
        # brace extraction fallback
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            candidates.append(raw[start:end + 1])

        for cand in candidates:
            try:
                data = json.loads(cand)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        raise ReplyParseError("Failed to parse LLM reply as JSON")

    REPLY_JSON_SCHEMA: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "spoken_text": {
                "type": "string",
                "description": "Speakable text, <=240 characters",
                "maxLength": 240,
            },
            "display_text": {
                "type": "string",
                "description": "Display text (optional, defaults to spoken_text)",
            },
            "emotion": {
                "type": "string",
                "enum": ["neutral", "happy", "excited", "affectionate", "curious", "listening", "thinking", "surprised", "confused", "sad", "frustrated", "sleepy", "sleeping", "speaking", "embarrassed", "alert"],
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