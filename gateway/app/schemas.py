"""Pinned wire contracts (schemas + provider protocols). Other gateway units
implement against these; do not rename fields."""
from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, field_validator

from app.config import EMOTIONS


class ActionSpec(BaseModel):
    type: Literal["none", "vibrate", "remember", "forget", "proactive"] = "none"
    text: str | None = None          # for remember: fact text
    level: int | None = None         # vibration level
    ms: int | None = None
    raw: dict[str, Any] | None = None

class InteractRequest(BaseModel):
    conversation_id: str | None = None
    device_id: str = "core2"
    text: str | None = None
    audio_wav_b64: str | None = None      # optional inline mic audio (16k mono s16 wav)
    locale: str | None = None
    device_battery: int | None = None
    device_charging: bool | None = None
    tts: bool = True

    @field_validator("text")
    @classmethod
    def _t(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()[:1200]
        return v

    def has_input(self) -> bool:
        return bool(self.text or self.audio_wav_b64)


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = {}
    ok: bool = True
    detail: str | None = None            # short result summary for trace


class AuraResponse(BaseModel):
    spoken_text: str
    display_text: str | None = None
    emotion: str = "neutral"
    expression_intensity: float = 1.0
    animation_hint: str | None = None
    action: ActionSpec | None = None
    conversation_id: str | None = None
    tool_trace: list[ToolCall] = []
    audio_wav_b64: str | None = None     # TTS result when requested
    stt_text: str | None = None          # what we heard (when audio path used)
    provider: str | None = None

    @field_validator("emotion", mode="before")
    @classmethod
    def _map_emotion(cls, v: Any) -> str:
        s = str(v or "neutral").strip().lower()
        return s if s in EMOTIONS else "neutral"

    @field_validator("expression_intensity", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> float:
        try:
            return min(1.0, max(0.0, float(v)))
        except (TypeError, ValueError):
            return 1.0


class DeviceStats(BaseModel):
    device_id: str = "core2"
    online: bool = True
    battery: int | None = None
    charging: bool | None = None
    rssi: int | None = None
    ip: str | None = None
    ssid: str | None = None
    fw_version: str | None = None
    free_heap: int | None = None
    uptime_s: int | None = None


class TTSRequest(BaseModel):
    text: str = ""
    voice: str | None = None


class WakeRequest(BaseModel):
    """Base64-encoded mono s16 WAV chunk from the device's VAD gate."""
    audio_b64: str = ""
    client_id: str | None = None


class WakeResponse(BaseModel):
    woke: bool = False
    reason: str = "disabled"
    text: str | None = None
    stt_provider: str | None = None
    ack_text: str | None = None          # short acknowledgment on match
    ack_emotion: str | None = None       # emotion coordinating the ack


class ProviderSwitchRequest(BaseModel):
    provider: str = ""


class HealthOut(BaseModel):
    ok: bool = True
    llm: str = "unknown"
    stt: str = "unknown"
    tts: str = "unknown"


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    async def generate_reply(
        self, system_prompt: str, messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None, json_schema: dict[str, Any] | None,
        timeout_s: float,
    ) -> dict[str, Any]: ...
    async def health(self, timeout_s: float = 5.0) -> bool: ...


@runtime_checkable
class STTProvider(Protocol):
    name: str
    async def transcribe(self, wav: bytes, timeout_s: float = 20.0) -> str: ...
    async def health(self, timeout_s: float = 5.0) -> bool: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    async def synthesize(self, text: str, timeout_s: float = 15.0) -> bytes: ...
    async def health(self, timeout_s: float = 5.0) -> bool: ...


@runtime_checkable
class ToolPlugin(Protocol):
    name: str
    read_only: bool
    def spec(self) -> dict[str, Any]: ...
    async def call(self, args: dict[str, Any], timeout_s: float) -> dict[str, Any]: ...
