import pytest

from app.config import Settings
from app.personality import build_personality, Persona, EXAMPLE_DIALOGUES


def test_build_personality_default() -> None:
    """Test building default personality."""
    settings = Settings()
    personality = build_personality(settings)
    assert isinstance(personality, Persona)
    assert personality.name == "AURA"


def test_build_personality_custom() -> None:
    """Test building custom personality."""
    settings = Settings(persona="dry_wit")
    personality = build_personality(settings)
    assert isinstance(personality, Persona)


def test_system_prompt_with_tools() -> None:
    """Test system prompt with tools."""
    settings = Settings()
    personality = build_personality(settings)
    
    tools = [
        {"name": "get_weather", "description": "Get weather"},
        {"name": "set_reminder", "description": "Set a reminder"},
    ]
    
    prompt = personality.build_system_prompt(tools)
    
    assert "You are AURA" in prompt
    assert "Available tools: 2 tools are available" in prompt
    assert "get_weather" in prompt
    assert "set_reminder" in prompt


def test_system_prompt_no_tools() -> None:
    """Test system prompt without tools."""
    settings = Settings()
    personality = build_personality(settings)
    
    prompt = personality.build_system_prompt(None)
    
    assert "You are AURA" in prompt
    assert "Available tools:" not in prompt


def test_example_dialogues() -> None:
    """Test example dialogues are properly formatted."""
    assert len(EXAMPLE_DIALOGUES) == 5
    
    for dialogue in EXAMPLE_DIALOGUES:
        assert "user" in dialogue
        assert "assistant" in dialogue
        
        # Check JSON format in assistant responses
        import json
        try:
            response = json.loads(dialogue["assistant"])
        except json.JSONDecodeError:
            pytest.fail("Assistant response is not valid JSON")
        
        # Check required fields
        required_fields = ["spoken_text", "display_text", "emotion", "expression_intensity", "animation_hint", "action"]
        for field in required_fields:
            assert field in response, f"Missing field: {field}"


def test_personality_config() -> None:
    """Test personality configuration."""
    settings = Settings(pet_name="Buddy")
    personality = build_personality(settings)
    
    assert personality.play_name == "Buddy"
    assert f"{personality.play_name}" in personality.build_system_prompt()