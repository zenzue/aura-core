"""HTTP handlers. Real provider calls only; no placeholder AI/STT/TTS.
Missing provider => explicit error, never a fabricated result."""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List

from litestar import Request, get, post

from app.config import Settings
from app.schemas import (
    AuraResponse,
    DeviceStats,
    InteractRequest,
    TTSRequest,
    ToolCall as ToolCallSchema,
)

logger = logging.getLogger(__name__)


def _state(request: Request):
    return request.app.state


def _provider_name(obj) -> str | None:
    name = getattr(obj, "name", None)
    return name if isinstance(name, str) else None


def _err(text: str) -> AuraResponse:
    return AuraResponse(
        spoken_text=text,
        display_text=text,
        emotion="neutral",
        expression_intensity=0.7,
        animation_hint="none",
        action=None,
    )


async def health_check(request: Request) -> Dict[str, Any]:
    return {"ok": True}


async def status(request: Request) -> Dict[str, Any]:
    state = _state(request)
    settings: Settings = state.settings

    async def _h(provider: Any) -> Dict[str, Any]:
        if provider is None:
            return {"healthy": False, "provider": "disabled"}
        name = str(getattr(provider, "name", "unknown"))
        try:
            ok = bool(await provider.health(timeout_s=5.0))
        except Exception:  # noqa: BLE001
            ok = False
        return {"healthy": ok, "provider": name}

    return {
        "llm": await _h(state.llm),
        "stt": await _h(state.stt),
        "tts": await _h(state.tts),
    }


async def device_stats(request: Request, data: DeviceStats) -> Dict[str, Any]:
    state = _state(request)
    merged = {k: v for k, v in data.model_dump().items() if v is not None}
    state.devstats.update(merged)
    return {"status": "updated"}


async def tts_generate(request: Request, data: TTSRequest) -> AuraResponse:
    state = _state(request)
    if state.tts is None:
        logger.warning("tts endpoint requested but no provider configured")
        return _err("speech synthesis is not configured on this gateway")
    try:
        wav = await state.tts.synthesize(data.text, timeout_s=60.0)
    except Exception as exc:  # noqa: BLE001
        logger.error("tts failed: %s", exc)
        return _err("speech synthesis failed")
    audio_b64 = base64.b64encode(wav).decode("ascii") if wav else None
    return AuraResponse(
        spoken_text=data.text,
        display_text=data.text,
        emotion="neutral",
        expression_intensity=0.7,
        animation_hint="none",
        action=None,
        audio_wav_b64=audio_b64,
        provider=_provider_name(state.tts),
    )


async def interact(request: Request, data: InteractRequest) -> AuraResponse:
    state = _state(request)
    settings: Settings = state.settings

    if not data.has_input():
        return _err("I did not receive any input")

    user_text: str | None = data.text or None
    stt_text: str | None = None

    # STT: only when audio supplied; explicit text does NOT fake a transcript.
    if data.audio_wav_b64 and not user_text:
        if state.stt is None:
            logger.warning("interact: audio input but no STT provider")
            return _err("voice input is not configured on this gateway")
        try:
            wav = base64.b64decode(data.audio_wav_b64)
        except Exception:
            return _err("audio data could not be decoded")
        if len(wav) > settings.max_audio_bytes:
            return _err("audio is too large")
        try:
            stt_text = (await state.stt.transcribe(wav, timeout_s=20.0) or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("stt failed: %s", exc)
            return _err("I could not understand the audio")
        if not stt_text:
            return _err("I did not catch that")
        user_text = stt_text

    if not user_text:
        return _err("I did not receive any input")

    if state.llm is None:
        logger.error("interact: no LLM provider configured")
        return AuraResponse(
            spoken_text="AI service unavailable",
            display_text="AI service unavailable — no model provider configured",
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action=None,
            stt_text=stt_text,
        )

    # history
    messages: List[Dict[str, str]] = []
    if state.memory is not None and settings.enable_memory and data.conversation_id:
        try:
            hist = await state.memory.recent_messages(
                data.conversation_id, limit=settings.history_max_messages
            )
            messages.extend(
                {"role": m["role"], "content": m["content"]}
                for m in hist
                if isinstance(m, dict)
                and m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory history load failed: %s", exc)
    messages.append({"role": "user", "content": user_text})

    # system prompt + tools
    system_prompt: str | None = None
    try:
        from app.personality import build_personality

        tools_spec = None
        if state.tools is not None:
            try:
                tools_spec = state.tools.specs_for_llm()
            except Exception as exc:  # noqa: BLE001
                logger.warning("tool specs failed: %s", exc)
        system_prompt = build_personality(settings).build_system_prompt(tools_spec)
    except Exception as exc:  # noqa: BLE001
        logger.warning("personality build failed: %s", exc)
        tools_spec = None

    # LLM
    try:
        raw = await state.llm.generate_reply(
            messages=messages,
            tools=tools_spec,
            system_prompt=system_prompt,
        )
        reply = state.llm.parse_llm_reply(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM processing failed: %s", exc)
        return AuraResponse(
            spoken_text="Sorry, I'm having trouble processing your request",
            display_text="LLM processing error",
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action=None,
            stt_text=stt_text,
        )

    spoken = str(reply.get("spoken_text") or "").strip()
    if not spoken:
        return AuraResponse(
            spoken_text="Sorry, I received an empty reply",
            display_text="Empty LLM reply",
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action=None,
            stt_text=stt_text,
        )
    display = str(reply.get("display_text") or spoken)
    emotion = str(reply.get("emotion") or "neutral")
    intensity = float(reply.get("expression_intensity") or 1.0)
    animation_hint = reply.get("animation_hint") if isinstance(reply.get("animation_hint"), str) else None

    max_chars = settings.max_spoken_chars
    if len(spoken) > max_chars:
        spoken = spoken[: max_chars - 3] + "..."
    if len(display) > settings.max_spoken_chars:
        display = display[: max_chars - 3] + "..."

    # tool calls requested by the model
    tool_trace: List[Any] = []
    for call in reply.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "")
        args = call.get("arguments") or call.get("args") or {}
        if not name:
            continue
        if state.tools is None:
            tool_trace.append(ToolCallSchema(name=name, args=args, ok=False, detail="tools disabled"))
            continue
        try:
            res = await state.tools.call(name=name, args=args, timeout_s=settings.tool_timeout_s)
            tool_trace.append(ToolCallSchema(
                name=name, args=args, ok=bool(res.get("ok", True)),
                detail=str(res.get("detail", ""))[:120],
            ))
        except Exception as exc:  # noqa: BLE001
            tool_trace.append(ToolCallSchema(name=name, args=args, ok=False, detail=str(exc)[:120]))

    # optional TTS
    audio_b64: str | None = None
    if data.tts and state.tts is not None:
        try:
            wav = await state.tts.synthesize(spoken, timeout_s=60.0)
            audio_b64 = base64.b64encode(wav).decode("ascii") if wav else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("interact TTS failed: %s", exc)
    elif data.tts:
        logger.info("interact: TTS requested but provider not configured")

    # memory
    if state.memory is not None and settings.enable_memory and data.conversation_id:
        try:
            await state.memory.append_message(
                data.conversation_id, {"role": "user", "content": user_text}
            )
            await state.memory.append_message(
                data.conversation_id, {"role": "assistant", "content": display}
            )
            await state.memory.maybe_summarize(state.llm, data.conversation_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory append failed: %s", exc)

    return AuraResponse(
        spoken_text=spoken,
        display_text=display,
        emotion=emotion,
        expression_intensity=intensity,
        animation_hint=animation_hint,
        action=None,
        conversation_id=data.conversation_id,
        tool_trace=tool_trace,
        audio_wav_b64=audio_b64,
        stt_text=stt_text,
        provider=_provider_name(state.llm),
    )


def build_routes():
    """Fresh handler objects per app (route handlers are per-Litestar-app)."""
    return [
        get(path="/healthz")(health_check),
        get(path="/v1/status")(status),
        post(path="/v1/interact", status_code=200)(interact),
        post(path="/v1/device_stats", status_code=200)(device_stats),
        post(path="/v1/tts", status_code=200)(tts_generate),
    ]
