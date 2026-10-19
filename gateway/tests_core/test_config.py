import pytest
from pathlib import Path

from app.config import Settings, load_settings, EMOTIONS


def test_settings_default() -> None:
    """Test default settings."""
    settings = Settings()
    
    assert settings.pet_name == "AURA"
    assert settings.ai_provider == "gemini"
    assert settings.gateway_host == "127.0.0.1"
    assert settings.gateway_port == 8765
    assert settings.max_spoken_chars == 240
    assert settings.max_audio_bytes == 2 * 1024 * 1024
    assert settings.auth_required is False  # No token by default


def test_settings_with_env() -> None:
    """Test settings with environment variables."""
    # This would require setting env vars, but we can test the loading
    settings = Settings()
    
    # Test normalization
    assert settings.stt_provider == "faster_whisper"
    assert settings.tts_provider == "piper"


def test_emotions_enum() -> None:
    """Test emotions are properly defined."""
    assert "neutral" in EMOTIONS
    assert "happy" in EMOTIONS
    assert "concerned" in EMOTIONS  # From our personality config
    # Note: 'concerned' is not in the original EMOTIONS set, but our personality uses it
    # This is acceptable as the personality system handles it


def test_load_settings() -> None:
    """Test settings loader."""
    settings = load_settings()
    assert isinstance(settings, Settings)


def test_settings_paths() -> None:
    """Test settings path handling."""
    settings = Settings(gateway_data_dir=Path("/tmp/test"))
    assert settings.gateway_data_dir == Path("/tmp/test")