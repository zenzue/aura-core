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
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    pet_name: str = Field("AURA", validation_alias="PET_NAME")
    pet_personality: str = Field("playful_assistant", validation_alias="PET_PERSONALITY")
    pet_timezone: str = Field("Asia/Bangkok", validation_alias="PET_TIMEZONE")
    pet_default_city: str = Field("Bangkok", validation_alias="PET_DEFAULT_CITY")

    ai_provider: str = Field("gemini", validation_alias="AI_PROVIDER")
    gemini_api_key: str = Field("", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field("", validation_alias="GEMINI_MODEL")
    ollama_base_url: str = Field("http://127.0.0.1:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("", validation_alias="OLLAMA_MODEL")
    ollama_format: str = Field("json", validation_alias="OLLAMA_FORMAT")
    openai_compat_base_url: str = Field("", validation_alias="OPENAI_COMPAT_BASE_URL")
    openai_compat_api_key: str = Field("", validation_alias="OPENAI_COMPAT_API_KEY")
    openai_compat_model: str = Field("", validation_alias="OPENAI_COMPAT_MODEL")

    stt_provider: str = Field("faster_whisper", validation_alias="STT_PROVIDER")
    stt_model_size: str = Field("base", validation_alias="STT_MODEL_SIZE")
    tts_provider: str = Field("piper", validation_alias="TTS_PROVIDER")
    tts_voice_path: str = Field("", validation_alias="TTS_VOICE_PATH")
    tts_voice: str = Field("en_US-lessac-medium", validation_alias="TTS_VOICE")

    gemini_temperature: float = Field(0.7, validation_alias="GEMINI_TEMPERATURE")
    gemini_top_p: float = Field(0.9, validation_alias="GEMINI_TOP_P")
    ollama_temperature: float = Field(0.8, validation_alias="OLLAMA_TEMPERATURE")
    ollama_top_p: float = Field(0.9, validation_alias="OLLAMA_TOP_P")
    openai_temperature: float = Field(0.7, validation_alias="OPENAI_TEMPERATURE")

    gateway_host: str = Field("127.0.0.1", validation_alias="GATEWAY_HOST")
    gateway_port: int = Field(8765, validation_alias="GATEWAY_PORT")
    device_auth_token: str = Field("", validation_alias="DEVICE_AUTH_TOKEN")
    gateway_data_dir: Path = Field(Path("./data"), validation_alias="GATEWAY_DATA_DIR")

    weather_default_lat: float = Field(13.75, validation_alias="WEATHER_DEFAULT_LAT")
    weather_default_lon: float = Field(100.50, validation_alias="WEATHER_DEFAULT_LON")

    enable_memory: bool = Field(True, validation_alias="ENABLE_MEMORY")
    enable_weather: bool = Field(True, validation_alias="ENABLE_WEATHER")
    enable_network_diagnostics: bool = Field(True, validation_alias="ENABLE_NETWORK_DIAGNOSTICS")
    enable_server_monitoring: bool = Field(False, validation_alias="ENABLE_SERVER_MONITORING")
    enable_proactive_speech: bool = Field(False, validation_alias="ENABLE_PROACTIVE_SPEECH")

    # runtime/limits
    max_spoken_chars: int = Field(240, validation_alias="MAX_SPOKEN_CHARS")
    max_audio_bytes: int = Field(2 * 1024 * 1024, validation_alias="MAX_AUDIO_BYTES")
    llm_timeout_s: float = Field(30.0, validation_alias="LLM_TIMEOUT_S")
    tool_timeout_s: float = Field(10.0, validation_alias="TOOL_TIMEOUT_S")
    rate_limit_per_min: int = Field(60, validation_alias="RATE_LIMIT_PER_MIN")
    history_max_messages: int = Field(200, validation_alias="HISTORY_MAX_MESSAGES")
    summarise_every: int = Field(20, validation_alias="SUMMARISE_EVERY")

    @field_validator("stt_provider", "tts_provider", "ai_provider")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower().replace("-", "_")

    @property
    def auth_required(self) -> bool:
        return bool(self.device_auth_token)


def load_settings() -> Settings:  # helper used by app factory
    return Settings()
