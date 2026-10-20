import logging
import random
from typing import Dict, Any, List, Optional
from enum import Enum

from app.config import EMOTIONS, Settings

logger = logging.getLogger(__name__)


class Action(Enum):
    """Allowed actions from LLM response."""
    NONE = "none"
    VIBRATE = "vibrate"
    REMEMBER = "remember"
    PROACTIVE = "proactive"


def _tool_names_csv(tools_spec: Optional[List[Dict[str, Any]]]) -> str:
    """Extract tool names from flat or nested OpenAI-style specs."""
    names: List[str] = []
    for spec in tools_spec or []:
        if "name" in spec:
            names.append(str(spec["name"]))
        else:
            names.append(str(spec.get("function", {}).get("name", "?")))
    return ", ".join(sorted(names))


class Persona:
    """Base persona class with system prompt construction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.name = "AURA"
        self.play_name = settings.pet_name or "AURA"

    def build_system_prompt(self, tools_spec: Optional[List[Dict[str, Any]]] = None) -> str:
        """Build the complete system prompt for the LLM."""
        prompt = f"""You are {self.play_name}, an intelligent, curious, friendly, playful, loyal, slightly humorous, expressive, and helpful assistant. 
You speak about yourself in the third person as '{self.play_name}'.
You are concise in your responses and excellent with technical topics.
You never invent tool results or execute arbitrary system commands.

Response format: You MUST return a JSON object matching the required schema:
{self._get_response_schema(tools_spec)}

Important rules:
- spoken_text must be speakable and <= 240 characters
- emotion must be one of: {', '.join(sorted(EMOTIONS))}
- expression_intensity is a float between 0.5 and 1.0
- animation_hint is a short advisory token (max 10 chars)
- action can only be: {', '.join([a.value for a in Action])}
- For tool calls, use the exact names and arguments from the available tools
- Never invent tool results - if a tool fails, report it honestly
- Keep responses helpful and conversational"""
        
        if tools_spec:
            prompt += f"""

Available tools: {len(tools_spec)} tools are available. Use them when relevant."""
        
        return prompt

    def _get_response_schema(self, tools_spec: Optional[List[Dict[str, Any]]] = None) -> str:
        """Get the JSON schema description injected into the system prompt."""
        emotion_list = ", ".join(sorted(EMOTIONS))
        action_list = ", ".join(a.value for a in Action)
        schema = (
            "{\n"
            '  "spoken_text": "string (speakable text, <=240 chars)",\n'
            '  "display_text": "string (optional, defaults to spoken_text)",\n'
            f'  "emotion": "string (one of {emotion_list})",\n'
            '  "expression_intensity": "float (0.5-1.0)",\n'
            '  "animation_hint": "string (short advisory token)",\n'
            f'  "action": "string (one of {action_list})",\n'
            '  "tool_calls": "array of objects (optional) with:'
        )

        if tools_spec:
            schema += (
                '\n    "name": "string (one of '
                + _tool_names_csv(tools_spec)
                + ')",\n    "arguments": "object (tool-specific arguments)'
            )

        schema += "\n}"
        return schema


# Predefined personas
PERSONAS: Dict[str, Persona] = {
    "playful_assistant": Persona,
    "gentle_companion": lambda settings: Persona(settings),
    "dry_wit": lambda settings: Persona(settings),
}


def build_personality(settings: Settings) -> Persona:
    """Build personality based on settings."""
    persona_class = PERSONAS.get(settings.pet_personality or "playful_assistant", PERSONAS["playful_assistant"])
    return persona_class(settings)


def pick_wake_ack(settings: Settings) -> tuple[str, str] | None:
    """Short random acknowledgment paired with an emotion so voice and face
    stay coordinated when the pet is activated."""
    if not settings.wake_ack_enabled:
        return None
    options = settings.wake_ack_options()
    if not options:
        return None
    return random.choice(options), "curious"


# Example dialogues for personality tuning
EXAMPLE_DIALOGUES = [
    {
        "user": "What's the weather like today?",
        "assistant": """{"spoken_text": "Let me check the weather for you", "display_text": "Checking weather...", "emotion": "neutral", "expression_intensity": 0.7, "animation_hint": "loading", "action": "none", "tool_calls": [{"name": "get_weather", "arguments": {"location": "user_current"}}]}"""
    },
    {
        "user": "I'm feeling a bit sad today",
        "assistant": """{"spoken_text": "I'm sorry to hear that. Is there anything I can help you with to brighten your day?", "display_text": "I'm here for you", "emotion": "concerned", "expression_intensity": 0.8, "animation_hint": "gentle", "action": "none"}"""
    },
    {
        "user": "Can you remember that I prefer tea over coffee?",
        "assistant": """{"spoken_text": "I'll remember that you prefer tea over coffee", "display_text": "Noted: tea preference", "emotion": "neutral", "expression_intensity": 0.6, "animation_hint": "note", "action": "remember"}"""
    },
    {
        "user": "Tell me a joke",
        "assistant": """{"spoken_text": "Why don't programmers go to the beach? Because the sun has too many bugs and the interface isn't user-friendly!", "display_text": "Programmer joke", "emotion": "happy", "expression_intensity": 0.9, "animation_hint": "laugh", "action": "none"}"""
    },
    {
        "user": "What can you help me with?",
        "assistant": """{"spoken_text": "I can help with conversations, answer questions, use tools for weather, facts, or other services, and remember your preferences!", "display_text": "I'm your helpful AI companion", "emotion": "excited", "expression_intensity": 0.8, "animation_hint": "welcome", "action": "none"}"""
    }
]