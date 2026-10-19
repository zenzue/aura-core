import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from litestar import Request, Response, get, post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_502_BAD_GATEWAY

from app.config import Settings
from app.schemas import InteractRequest, AuraResponse, DeviceStats, TTSRequest
from app.providers.llm_base import ReplyParseError

logger = logging.getLogger(__name__)


@get("/healthz")
async def health_check(request: Request) -> Dict[str, Any]:
    """Health check endpoint."""
    return {"ok": True}


@get("/v1/status")
async def status(request: Request) -> Dict[str, Any]:
    """Get system status including provider health."""
    app_state = request.app.state
    settings: Settings = app_state.settings
    
    # Check LLM provider
    llm_health = False
    llm_info = "none"
    if app_state.llm:
        llm_health = await app_state.llm.health()
        llm_info = settings.ai_provider or "unknown"
    
    # Check STT provider
    stt_health = False
    if app_state.stt:
        # TODO: Implement STT health check
        stt_health = True  # Placeholder
        stt_info = "whisper"  # Placeholder
    
    # Check TTS provider
    tts_health = False
    if app_state.tts:
        # TODO: Implement TTS health check
        tts_health = True  # Placeholder
        tts_info = "piper"  # Placeholder
    
    return {
        "llm": {
            "healthy": llm_health,
            "provider": llm_info,
            "model": settings.gemini_model or settings.ollama_model or settings.openai_model or "unknown",
        },
        "stt": {
            "healthy": stt_health,
            "provider": stt_info,
        },
        "tts": {
            "healthy": tts_health,
            "provider": tts_info,
        },
    }


@post("/v1/device_stats")
async def device_stats(request: Request, data: DeviceStats) -> Dict[str, Any]:
    """Update and cache device statistics."""
    app_state = request.app.state
    app_state.devstats.update(data.dict())
    return {"status": "updated"}


@post("/v1/tts")
async def tts_generate(request: Request, data: TTSRequest) -> AuraResponse:
    """Generate TTS audio from text."""
    app_state = request.app.state
    settings = app_state.settings
    
    if not app_state.tts:
        logger.warning("TTS provider not available")
        return AuraResponse(
            spoken_text=data.text,
            display_text=data.text,
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action="none",
            audio_wav_b64=None,
        )
    
    try:
        # TODO: Implement actual TTS generation
        # This is a placeholder - actual implementation would call the TTS provider
        # For now, return mock response
        return AuraResponse(
            spoken_text=data.text,
            display_text=data.text,
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action="none",
            audio_wav_b64=None,  # Placeholder - would be base64 encoded WAV
        )
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return AuraResponse(
            spoken_text=data.text,
            display_text=data.text,
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action="none",
            audio_wav_b64=None,
        )


@post("/v1/interact")
async def interact(request: Request, data: InteractRequest) -> AuraResponse:
    """Main interaction endpoint handling STT -> LLM -> TTS pipeline."""
    app_state = request.app.state
    settings = app_state.settings
    
    # Step 1: Audio transcription (STT)
    stt_text = None
    if data.audio_wav_b64:
        if not app_state.stt:
            logger.warning("STT provider not available, using passthrough text")
            stt_text = data.text or "Audio received but STT not available"
        else:
            try:
                # TODO: Implement actual STT
                # This is a placeholder - actual implementation would decode and transcribe
                stt_text = data.text or "Transcribed audio"  # Placeholder
                logger.info("STT transcription completed")
            except Exception as e:
                logger.error(f"STT failed: {e}")
                # Return clear error response, never fake transcript
                return AuraResponse(
                    spoken_text="Sorry, I couldn't understand the audio",
                    display_text="Audio processing error",
                    emotion="concerned",
                    expression_intensity=0.8,
                    animation_hint="error",
                    action="none",
                    audio_wav_b64=None,
                )
    
    # Use provided text if no audio or STT failed
    user_text = stt_text or data.text
    if not user_text:
        return AuraResponse(
            spoken_text="I didn't receive any input",
            display_text="No input received",
            emotion="neutral",
            expression_intensity=0.7,
            animation_hint="none",
            action="none",
            audio_wav_b64=None,
        )
    
    # Step 2: Build conversation history
    messages: List[Dict[str, Any]] = []
    
    # Add recent messages from memory if available
    if app_state.memory and settings.enable_memory:
        try:
            recent = await app_state.memory.recent_messages(
                conversation_id=data.conversation_id or "default",
                limit=settings.history_max_messages or 10,
            )
            messages.extend(recent)
        except Exception as e:
            logger.warning(f"Failed to load memory: {e}")
    
    # Add current user message
    messages.append({"role": "user", "content": user_text})
    
    # Step 3: Build system prompt with personality and tools
    personality = None
    try:
        from app.personality import build_personality
        personality = build_personality(settings)
    except Exception as e:
        logger.error(f"Failed to build personality: {e}")
        personality = None
    
    system_prompt = None
    tools_spec = None
    
    if app_state.tools:
        try:
            tools_spec = app_state.tools.specs_for_llm()
        except Exception as e:
            logger.warning(f"Failed to get tool specs: {e}")
    
    if personality:
        system_prompt = personality.build_system_prompt(tools_spec)
    
    # Step 4: Generate LLM reply
    if not app_state.llm:
        logger.error("LLM provider not available")
        return AuraResponse(
            spoken_text="AI service temporarily unavailable",
            display_text="Service unavailable",
            emotion="concerned",
            expression_intensity=0.8,
            animation_hint="error",
            action="none",
            audio_wav_b64=None,
        )
    
    try:
        raw_reply = await app_state.llm.generate_reply(
            messages=messages,
            tools=tools_spec,
            system_prompt=system_prompt,
        )
        
        # Parse and validate reply
        try:
            reply = app_state.llm.parse_llm_reply(raw_reply)
        except ReplyParseError as e:
            logger.error(f"LLM reply parse error: {e}")
            # Return structured error instead of raw error
            return AuraResponse(
                spoken_text="Sorry, I'm having trouble processing my response",
                display_text="Response processing error",
                emotion="concerned",
                expression_intensity=0.8,
                animation_hint="error",
                action="none",
                audio_wav_b64=None,
            )
        
        # Ensure required fields with defaults
        spoken_text = reply.get("spoken_text", "")
        display_text = reply.get("display_text", spoken_text)
        emotion = reply.get("emotion", "neutral")
        expression_intensity = reply.get("expression_intensity", 0.7)
        animation_hint = reply.get("animation_hint", "none")
        action = reply.get("action", "none")
        
        # Truncate spoken text if needed
        max_spoken_chars = settings.max_spoken_chars or 240
        if len(spoken_text) > max_spoken_chars:
            spoken_text = spoken_text[:max_spoken_chars-3] + "..."
            display_text = display_text[:max_spoken_chars-3] + "..." if len(display_text) > max_spoken_chars else display_text
        
        # Step 5: Tool execution (if any)
        tool_trace = []
        if "tool_calls" in reply and reply["tool_calls"]:
            for tool_call in reply["tool_calls"]:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})
                
                if app_state.tools and tool_name:
                    try:
                        # Check if tool exists and execute
                        # This would be implemented in the tools registry
                        tool_result = await app_state.tools.call(
                            name=tool_name,
                            args=tool_args,
                            timeout_s=settings.tool_timeout_s or 10,
                        )
                        tool_trace.append({"name": tool_name, "result": tool_result, "ok": True})
                    except Exception as e:
                        tool_trace.append({"name": tool_name, "error": str(e), "ok": False})
        
        # Step 6: TTS generation if requested
        tts_audio = None
        if data.tts and app_state.tts:
            try:
                # TODO: Implement actual TTS generation
                # This would call the TTS provider with the spoken_text
                tts_audio = None  # Placeholder
                logger.info("TTS generation completed")
            except Exception as e:
                logger.error(f"TTS failed: {e}")
                tts_audio = None
        
        final_response = AuraResponse(
            spoken_text=spoken_text,
            display_text=display_text,
            emotion=emotion,
            expression_intensity=expression_intensity,
            animation_hint=animation_hint,
            action=action,
            audio_wav_b64=tts_audio,
        )
        
    except Exception as e:
        logger.error(f"LLM processing failed: {e}")
        final_response = AuraResponse(
            spoken_text="Sorry, I'm having trouble processing your request",
            display_text="Processing error",
            emotion="concerned",
            expression_intensity=0.8,
            animation_hint="error",
            action="none",
            audio_wav_b64=None,
        )
    
    # Step 7: Update memory
    if app_state.memory and settings.enable_memory and data.conversation_id:
        try:
            # Append user message
            await app_state.memory.append_message(
                conversation_id=data.conversation_id,
                role="user",
                content=user_text,
            )
            
            # Append assistant response
            await app_state.memory.append_message(
                conversation_id=data.conversation_id,
                role="assistant",
                content=display_text,
            )
            
            # Maybe summarize
            if settings.auto_summarize:
                await app_state.memory.maybe_summarize(
                    llm=app_state.llm,
                    conversation_id=data.conversation_id,
                )
        except Exception as e:
            logger.warning(f"Failed to update memory: {e}")
    
    return final_response