"""Gateway settings. Strict typed validation via pydantic-settings.

Deployment note: nothing here assumes the gateway or any LLM runs on the
developer Mac. Gateway, Ollama and llama.cpp may live on any reachable host
(Jetson Orin, AI Max, ...). API keys are SecretStr so they never leak into
logs/repr. The Core2 firmware never sees any LLM credential - it only holds
its device token and the gateway URL.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EMOTIONS = {
    "neutral", "happy", "excited", "affectionate", "curious", "listening",
    "thinking", "surprised", "confused", "sad", "frustrated", "sleepy",
    "sleeping", "speaking", "embarrassed", "alert",
}

# AI_PROVIDER accepts exactly gemini|ollama|llamacpp (legacy aliases normalized).
PROVIDER_ALIASES = {
    "openai_compat": "llamacpp",
    "openai_compatible": "llamacpp",
    "openai-compatible": "llamacpp",
    "llama.cpp": "llamacpp",
    "llama_cpp": "llamacpp",
    "llamacpp": "llamacpp",
    "gemini": "gemini",
    "ollama": "ollama",
}

AuthProviderMode = Literal["none", "bearer"]
ProviderName = Literal["gemini", "ollama", "llamacpp"]

WAKE_ACK_DEFAULT = "Yes?,I'm here.,You called?,What's up?,I'm listening."


def _is_valid_base_url(url: str) -> bool:
    """Absolute http(s) URL: bracketed IPv6, hostnames/FQDNs/IPv4, optional port."""
    if not url:
        return False
    m = re.match(
        r"^https?://"
        r"(?:\[[0-9a-fA-F:.%]+\]|[A-Za-z0-9\-._]+)"
        r"(?::\d{1,5})?"
        r"(?:/[^\s]*)?$",
        url,
    )
    if not m:
        return False
    try:
        hostseg = url.split("://", 1)[1].split("/", 1)[0]
        if ":" in hostseg and not hostseg.startswith("["):
            port = int(hostseg.rsplit(":", 1)[1])
            if not (1 <= port <= 65535):
                return False
    except (ValueError, IndexError):
        return False
    return True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        populate_by_name=True,
    )

    # ---- pet identity / behavior --------------------------------------------
    pet_name: str = Field("AURA")
    pet_personality: str = Field("playful_assistant")
    pet_timezone: str = Field("Asia/Bangkok")
    pet_default_city: str = Field("Bangkok")

    # ---- LLM provider selection (strict) ------------------------------------
    ai_provider: ProviderName = Field("gemini")

    gemini_api_key: SecretStr = Field(SecretStr(""))
    gemini_model: str = Field("gemini-2.5-flash")
    gemini_base_url: str = Field("")        # optional SDK-compatible override
    gemini_timeout_s: float = Field(30.0)
    gemini_temperature: float = Field(0.7)
    gemini_top_p: float = Field(0.9)

    # Ollama: native HTTP API (/api/chat, /api/tags). Never assumed to be local.
    ollama_base_url: str = Field("http://127.0.0.1:11434")
    ollama_model: str = Field("")
    ollama_api_key: SecretStr = Field(SecretStr(""))
    ollama_auth_mode: AuthProviderMode = Field("none")
    ollama_timeout_s: float = Field(45.0)
    ollama_temperature: float = Field(0.8)
    ollama_top_p: float = Field(0.9)

    # llama.cpp: OpenAI-compatible server (/v1/chat/completions, /v1/models).
    llamacpp_base_url: str = Field("http://127.0.0.1:8080/v1")
    llamacpp_model: str = Field("")
    llamacpp_api_key: SecretStr = Field(SecretStr(""))
    llamacpp_auth_mode: AuthProviderMode = Field("none")
    llamacpp_timeout_s: float = Field(45.0)
    llamacpp_temperature: float = Field(0.7)

    # Explicit optional failover. Cloud failover is OFF by default so a failing
    # local provider never silently sends private prompts to Gemini.
    llm_failover_chain: str = Field("")
    allow_cloud_failover: bool = Field(False)
    validate_model_ids: bool = Field(True)

    # ---- speech (independent of LLM provider) --------------------------------
    stt_provider: str = Field("faster_whisper")
    stt_model_size: str = Field("base")
    tts_provider: str = Field("piper")
    tts_voice_path: str = Field("")
    tts_voice: str = Field("en_US-lessac-medium")

    # ---- wake / acknowledgment ------------------------------------------------
    wake_enabled: bool = Field(False)
    wake_regex: str = Field(r"^(hey[ ,]*aura|aura[ ,]*robot|aura)\b")
    wake_max_audio_s: float = Field(10.0, validation_alias=AliasChoices(
        "wake_max_audio_s", "wake_max_audio_seconds"))
    wake_min_rms: float = Field(500.0)
    wake_ack_enabled: bool = Field(True)
    wake_ack_phrases: str = Field(WAKE_ACK_DEFAULT)

    # ---- gateway / network ---------------------------------------------------
    gateway_host: str = Field("127.0.0.1")
    gateway_port: int = Field(8765, ge=1, le=65535)
    gateway_data_dir: Path = Field(Path("./data"))
    tls_verify_outbound: bool = Field(True)
    llm_timeout_s: float = Field(30.0)      # legacy global cap
    tool_timeout_s: float = Field(10.0)
    rate_limit_per_min: int = Field(60)

    # ---- auth / admin ----------------------------------------------------------
    device_auth_token: str = Field("")       # device->gateway shared token
    admin_token: SecretStr = Field(SecretStr(""))  # gateway admin API token

    # ---- memory / tools / features --------------------------------------------
    enable_memory: bool = Field(True)
    enable_weather: bool = Field(True)
    enable_network_diagnostics: bool = Field(True)
    enable_server_monitoring: bool = Field(False)
    enable_proactive_speech: bool = Field(False)
    max_spoken_chars: int = Field(240)
    max_audio_bytes: int = Field(2 * 1024 * 1024)
    history_max_messages: int = Field(200)
    summarise_every: int = Field(20)

    # ---- weather ----------------------------------------------------------------
    weather_default_lat: float = Field(13.75)
    weather_default_lon: float = Field(100.50)

    # ---- logging ------------------------------------------------------------------
    log_level: str = Field("INFO")

    @field_validator("ai_provider", mode="before")
    @classmethod
    def _provider_alias(cls, v: object) -> object:
        s = str(v or "").strip().lower()
        return PROVIDER_ALIASES.get(s, s)

    @field_validator("stt_provider", "tts_provider")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower().replace("-", "_")

    @field_validator("gemini_base_url", "ollama_base_url", "llamacpp_base_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = (v or "").strip().rstrip("/")
        if not v:
            return ""
        if not _is_valid_base_url(v):
            raise ValueError(
                "not a valid absolute http(s) base URL (host/IPv4/IPv6/FQDN "
                "with optional port): " + repr(v)
            )
        return v

    @field_validator("gemini_timeout_s", "ollama_timeout_s", "llamacpp_timeout_s",
                     "llm_timeout_s", "tool_timeout_s", "wake_max_audio_s")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0 or v > 600:
            raise ValueError("timeout must be >0 and <=600 seconds")
        return float(v)

    @field_validator("gemini_temperature", "ollama_temperature", "llamacpp_temperature",
                     "gemini_top_p", "ollama_top_p")
    @classmethod
    def _range(cls, v: float) -> float:
        if not (0.0 <= float(v) <= 1.0):
            raise ValueError("sampling parameter must be within 0..1")
        return float(v)

    @model_validator(mode="after")
    def _wake_ack_default(self) -> "Settings":
        return self

    def problems(self) -> tuple[str, ...]:
        """Human-readable completeness problems for the ACTIVE provider.
        Surfaced via /v1/status so operators see why LLM is disabled; never
        raises at import so test/CLI settings construction stays possible."""
        p: list[str] = []
        if self.ai_provider == "gemini":
            if not self.gemini_api_key.get_secret_value():
                p.append("gemini selected but GEMINI_API_KEY is empty")
        elif self.ai_provider == "ollama":
            if not self.ollama_base_url:
                p.append("ollama selected but OLLAMA_BASE_URL is empty")
            if not self.ollama_model:
                p.append("ollama selected but OLLAMA_MODEL is empty")
            if self.ollama_auth_mode == "bearer" and not self.ollama_api_key.get_secret_value():
                p.append("ollama auth_mode=bearer requires OLLAMA_API_KEY")
        elif self.ai_provider == "llamacpp":
            if not self.llamacpp_base_url:
                p.append("llamacpp selected but LLAMACPP_BASE_URL is empty")
            if self.llamacpp_auth_mode == "bearer" and not self.llamacpp_api_key.get_secret_value():
                p.append("llamacpp auth_mode=bearer requires LLAMACPP_API_KEY")
        return tuple(p)

    def timeout_for(self, provider: str) -> float:
        if provider == "gemini":
            return self.gemini_timeout_s
        if provider == "ollama":
            return self.ollama_timeout_s
        if provider == "llamacpp":
            return self.llamacpp_timeout_s
        return self.llm_timeout_s

    @property
    def resolved_gemini_api_key(self) -> str:
        return self.gemini_api_key.get_secret_value() or os.getenv("GEMINI_API_KEY", "")

    @property
    def auth_required(self) -> bool:
        return bool(self.device_auth_token)

    @property
    def admin_api_enabled(self) -> bool:
        return bool(self.admin_token.get_secret_value())

    def wake_ack_options(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.wake_ack_phrases.split(",") if p.strip())


def load_settings() -> Settings:  # helper used by app factory
    return Settings()
