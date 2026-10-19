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
    async def health(self) -> bool:
        """Check if provider is healthy/reachable."""
        pass

    @classmethod
    def parse_llm_reply(cls, raw: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Parse raw LLM response into normalized format."""
        if isinstance(raw, dict):
            return raw
        
        try:
            # Try to parse as JSON
            data = json.loads(raw.strip())
            return data
        except json.JSONDecodeError:
            # Try to extract JSON from text
            raw = raw.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.endswith("```"):
                raw = raw[:-3]
            
            try:
                data = json.loads(raw)
                return data
            except json.JSONDecodeError as e:
                raise ReplyParseError(f"Failed to parse LLM reply: {e}")

    @staticmethod
    def REPLY_JSON_SCHEMA: Dict[str, Any] = {
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
                "enum": ["happy", "neutral", "concerned", "excited", "calm"],
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