"""One-shot insertion of the wake endpoint into app/api.py (run once)."""

f = 'app/api.py'
s = open(f).read()

if 'async def wake' in s:
    print('wake already present')
    raise SystemExit(0)

s = s.replace('import logging', 'import base64 as b64_mod\nimport logging', 1)
if 'import re' not in s.split('\n\n')[0] and '\nimport re\n' not in s:
    s = s.replace('import logging', 'import logging\nimport re', 1)

if 'from app.audio.wav_utils import' not in s:
    s = s.replace('from app.schemas import (',
                  'from app.audio.wav_utils import parse_wav, rms\nfrom app.schemas import (', 1)
if 'WakeRequest,' not in s:
    s = s.replace('from app.schemas import (\n',
                  'from app.schemas import (\n    WakeRequest,\n    WakeResponse,\n', 1)

handler = '''

async def wake(request: Request, data: WakeRequest) -> WakeResponse:
    """Gateway-side wake detection: transcribe a VAD-gated WAV chunk and match
    the configured wake regex. Honest errors only: disabled/no-STT return a
    reason, never fabricate detections. Opt-in via settings (docs/wake-word.md)."""
    settings: Settings = _state(request).settings
    if not settings.wake_enabled:
        return WakeResponse(woke=False, reason="disabled")

    stt = _state(request).stt
    if stt is None:
        return WakeResponse(woke=False, reason="no stt provider configured")

    try:
        wav = b64_mod.b64decode(data.audio_b64, validate=True)
    except Exception:
        return WakeResponse(woke=False, reason="invalid base64 audio")
    if not wav:
        return WakeResponse(woke=False, reason="empty audio")
    if len(wav) > int(settings.max_audio_bytes):
        return WakeResponse(woke=False, reason="audio too large")

    try:
        parsed = parse_wav(wav)
    except ValueError as exc:
        return WakeResponse(woke=False, reason=f"bad wav: {exc}")
    if rms(parsed.pcm) < settings.wake_min_rms:
        return WakeResponse(woke=False, reason="silence")

    try:
        text = await stt.transcribe(wav, timeout_s=settings.wake_max_audio_s + 10.0)
    except Exception as exc:  # noqa: BLE001
        logger.error("wake: stt failed: %s", exc)
        return WakeResponse(woke=False, reason="stt failed")

    text = text.strip()
    if not text:
        return WakeResponse(woke=False, reason="no speech", stt_provider=stt.name)
    woke = bool(re.search(settings.wake_regex, text, flags=re.IGNORECASE))
    logger.info("wake check: text=%r woke=%s", text[:80], woke)
    return WakeResponse(woke=woke, reason="match" if woke else "no match",
                        text=text, stt_provider=stt.name)

'''
anchor = '\nasync def device_stats'
if anchor not in s:
    anchor = '\nasync def tts_generate'
    s = s.replace(anchor, handler + '\n' + anchor.lstrip('\n'), 1)
else:
    s = s.replace(anchor, handler + '\n' + anchor.lstrip('\n'), 1)

open(f, 'w').write(s)
print('wake handler inserted')
