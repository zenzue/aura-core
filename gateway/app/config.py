"""Gateway core settings (pinned contract). Env-driven, validated at startup."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EMOTIONS = {
    "neutral", "happy", "excited", "affectionate", "curious", "listening",
    "thinking", "surprised", "confused", "sad", "frustrated", "sleepy",
    "sleeping", "speaking", "embarrassed", "alert",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    pet_name: str = Field("AURA")
    pet_personality: str = Field("playful_assistant")
    pet_timezone: str = Field("Asia/Bangkok")
    pet_default_city: str = Field("Bangkok")

    ai_provider: str = Field("gemini")
    gemini_api_key: str = Field("")
    gemini_model: str = Field("")
    ollama_base_url: str = Field("http://127.0.0.1:11434")
    ollama_model: str = Field("")
    ollama_format: str = Field("json")
    openai_compat_base_url: str = Field("")
    openai_compat_api_key: str = Field("")
    openai_compat_model: str = Field("")

    stt_provider: str = Field("faster_whisper")
    stt_model_size: str = Field("base")
    tts_provider: str = Field("piper")
    tts_voice_path: str = Field("")
    tts_voice: str = Field("en_US-lessac-medium")

    gemini_temperature: float = Field(0.7)
    gemini_top_p: float = Field(0.9)
    ollama_temperature: float = Field(0.8)
    ollama_top_p: float = Field(0.9)
    openai_temperature: float = Field(0.7)

    gateway_host: str = Field("127.0.0.1")
    gateway_port: int = Field(8765)
    device_auth_token: str = Field("")
    gateway_data_dir: Path = Field(Path("./data"))

    weather_default_lat: float = Field(13.75)
    weather_default_lon: float = Field(100.50)

    enable_memory: bool = Field(True)
    enable_weather: bool = Field(True)
    enable_network_diagnostics: bool = Field(True)
    enable_server_monitoring: bool = Field(False)
    enable_proactive_speech: bool = Field(False)

    # runtime/limits
    max_spoken_chars: int = Field(240)
    max_audio_bytes: int = Field(2 * 1024 * 1024)
    llm_timeout_s: float = Field(30.0)
    tool_timeout_s: float = Field(10.0)
    rate_limit_per_min: int = Field(60)
    history_max_messages: int = Field(200)
    summarise_every: int = Field(20)

    @field_validator("stt_provider", "tts_provider", "ai_provider")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower().replace("-", "_")

    @property
    def auth_required(self) -> bool:
        return bool(self.device_auth_token)


def load_settings() -> Settings:  # helper used by app factory
    return Settings()
