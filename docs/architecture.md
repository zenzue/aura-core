# AURA Architecture

AI robot pet & personal assistant on **M5Stack Core2** (original ESP32) with a Python **AI gateway**.

> Traceability rule used throughout this project: a feature is `planned`, `compile-verified`,
> `sim-verified`, or `hardware-verified`. Only the last is tested on a device. We never mark
> microphone/speaker/wake-word features hardware-verified without a real run. See
> `docs/hardware-verification.md`.

## 1. Design principles

1. **Device = expressive pet + I/O terminal. Gateway = intelligence.** No LLM on ESP32.
2. **Local life offline.** Face, emotion, idle behavior, touch, tilt, battery awareness run
   with zero network. AI/voice features degrade gracefully when the gateway is unreachable.
3. **Half-duplex audio.** Core2's mic (I2S0 PDM RX) and speaker share the I2S0 controller;
   mic capture is suspended while the speaker plays (half-duplex state machine), never "both live".
4. **Animation never blocks.** Rendering runs on the Arduino/main task; all network/audio work
   happens on dedicated tasks, connected only via bounded queues.
5. **Nothing fake in production mode.** Providers return real API results or explicit errors.

## 2. Hardware ground truth (verified against library sources, Oct 2026)

Source-level research from `M5Unified` master (0.2.26) / `M5GFX` master (0.2.33) and Core2
schematic data. **Not yet device-verified.**

| Subsystem | Facts (as used by us) |
|---|---|
| Display | ILI9342C/E (not ILI9341), 320×240, RGB565, SPI; backlight via AXP PMU (`M5.Display.setBrightness`). Double buffering via `setBuffer` unavailable at full-res in SRAM → partial-region direct draws + small sprites. |
| Touch | FT5x06-family capacitive via I2C + `M5.Touch`: `getCount()`, `getDetail(i)` with `wasClicked()/wasPressed()/wasReleased()/isHolding()/wasHold()/isDragging()/x/y`. |
| Buttons | Core2 uses touch-buttons BtnA/B/C mapped on screen bottom in M5Unified (`M5.BtnA...`) **and** physical side buttons on Core2: BtnPWR GPIO14. Btn API: `wasClicked/wasReleasedAfterHold/isHolding/wasHold`. |
| Power | PMU AXP192 (older Core2) or AXP2101 (newer); `M5.Power.getBatteryLevel()`, `isCharging()`, `getBatteryVoltage()`, `setVibration(level)` (vibration motor via PMU). |
| IMU | MPU6886 via `M5.Imu.getAccel(ax,ay,az)`, `getGyro(...)` — tilt behaviors use accelerometer. |
| Mic | Built-in **PDM mic**: data GPIO34, PDM clock GPIO0 via `M5.Mic` (PDM mode, mono). `begin()`, async `record(int16_t* buf, size_t samples, rate, false)` fills buffer asynchronously; completion via `setBufferReleaseCallback()` (set it before first record); `isRecording()` 0/1/2. |
| Speaker | I2S amp (bck=12, ws=0, data=2) on **I2S0, same controller as the mic** → half-duplex. `M5.Speaker.begin()/setVolume()/playRaw(int16_t*, len, rate, stereo=false, repeat, channel, stop_cur)/playWav(buf,len)/tone()/isPlaying()/end()`. |
| PSRAM | Core2 has 8 MB PSRAM (DWD4 module) — used for record buffers, gateway JSON, asset staging. |
| Wi-Fi | 2.4 GHz only (802.11 b/g/n) — no 5 GHz advertised. |

Audio pipeline implications (locked design):
- One `AudioBus` owns both directions. States: `IDLE → (WAKE|PTT) → LISTENING → PROCESSING → SPEAKING → IDLE`.
- Mic start = `Mic.begin()`+queue record; stop = `Mic.end()`. Speaker start = `Speaker.begin()`; playback end tracked via release callback/`isPlaying()`; speaker teardown before mic restart.
- Record budget: **bounded** — PDM mono 16 kHz int16; max utterance 10 s ≈ 320 KB in PSRAM.

### Wake-word feasibility (Phase 5 input — honest summary pending final matrix)

- MultiNet voice-command engine: **not available** on classic ESP32 in current esp-sr (v2.x).
- esp-sr v2.x requires IDF 5.x ⇒ needs arduino-esp32 core 3.x (`pioarduino`/official espressif32 7.x+), not our current espressif32 6.13 baseline.
- WakeNet on classic ESP32: only the small "s" model variants are exposed by upstream Kconfig for esp32 in current esp-sr; M5Stack community esp-sr ports target S3/P4 only.
- Custom-name ("AURA") local wake training: Espressif's documented path is paid/registered customization; community TTS-pipeline tooling is unproven for classic ESP32.
- **Decision**: shipping baseline = touch-to-talk (hold BtnPWR/screen long-press) + gateway-side name detection as an opt-in privacy-explicit streaming mode. Local WakeNet (supported model only) explored on an experimental build-environment, never claimed without hardware proof. Full matrix: `docs/wake-word.md`.

## 3. Firmware design (PlatformIO, C++17)

```
firmware/
 platformio.ini            espressif32@6.13.0 board m5stack-core2; M5GFX 0.2.33 + M5Unified 0.2.26 pinned
 include/aura/core/        shared contracts: types, events, config keys, face rig, audio state
 src/main.cpp              app shell: boot, task spawn, main animation tick
 src/aura/anim/            easing, tween engine, EmotionEngine, expression library, behavior scheduler (PURE C++, no M5)
 src/aura/face/            FaceRenderer (M5GFX partial-region draws), status indicators
 src/aura/hal/             TouchInput, TiltMonitor, PowerMonitor, VibrationFeedback, ConfigStore(NVS)
 src/aura/audio/           AudioBus half-duplex, MicCapture, SpkPlayback, VAD(silence), WAV helpers, AudioDiags
 src/aura/net/             WifiManager(+provisioning later), GatewayClient(+auth later)
 src/aura/app/             PetApp state machine, Event bus wiring, Diagnostics
```

### Concurrency model

| Task | Core | Period | Notes |
|---|---|---|---|
| `app` (main) | 1 | 33 ms target (30 fps) | touch poll, animation tick, face render. Never blocks. |
| `audio` | 0 | event | owns Mic/Speaker; blocks freely. |
| `net` | 0 | event | HTTP/JSON to gateway; bounded queues (max 4 req), httpx-style timeouts 10 s. |
| `behav` | — | merged into app tick scheduler | idle behaviors, timers, quiet hours. |

All cross-task messaging = `EventBus` (FreeRTOS `QueueHandle_t` of fixed 32-byte events,
capacity 16, drop-oldest with log counter). No shared mutable structs.

### Face & emotion engine

Emotions (16): neutral, happy, excited, affectionate, curious, listening, thinking, surprised,
confused, sad, frustrated, sleepy, sleeping, speaking, embarrassed, alert.

- `FaceRigState` (pure data): per-eye `openness, gazeX/Y (−1..1), squint, widen, glow, pupilScale`; per-eye accent color; global `glowIntensity`, `browAngle`, `headTilt`.
- `EmotionEngine` maps Emotion → target rig params (randomized ranges) + blink profile (rate, blink-depth, double-blink probability) + idle glance profile; smooth transitions via tween (easeInOutCubic), **never** state jumps.
- Renderer draws only the changed regions: per-eye dirty rect (eye + glow + lid travel) ≈ eye box regions, background/gradient drawn once; status dots tiny and drawn only on change. Glows use layered `fillSmoothCircle` alpha fills — no per-pixel loops in hot path.
- AI may **suggest** an emotion; local machine validates/clamps and owns actual animation.

### AI contract (gateway ⇄ device)

`POST /v1/interact` — device sends: conversation_id, text or audio ref, device stats.
Validated gateway reply (`AuraResponse`): `spoken_text(≤240 chars)`, `display_text`,
`emotion(enum)`, `intensity(0..1)`, `animation_hint(string enum-ish, advisory only)`,
`action({type:"none|vibrate|remember|proactive"} params)`, `tool_trace`, `conversation_id`.
Device maps emotion locally; unknown fields ignored; invalid → safe fallback.

Gateway providers (independent axes — STT ≠ LLM ≠ TTS):
- LLM: `gemini` (official google-genai SDK, structured output via response_schema + function tools) or `ollama` (/api/chat with tools, `format:"json"` structured).
- STT: `faster_whisper` (WhisperModel, VAD filter) — models auto-download from HuggingFace first run; or `gemini` audio understanding via generate_content as one-stop alternative.
- TTS: `piper` (piper-tts 1.8.0 = maintained piper1-gpl, `PiperVoice.load`/`synthesize_wav`, voice models from HF `rhasspy/piper-voices`) or `gemini_tts` (native audio models via SpeechConfig; note: cloud → audio leaves LAN).

Security: device→gateway auth token header; gateway binds LAN; no credentials in device build;
TLS optional (documented plain-HTTP-on-LAN tradeoff); microphone only active in explicit listening
windows after wake/PTT; listening state always shown on screen; gateway rate-limits; nothing
shell/SSH from LLM output; tools read-only allowlisted. See `docs/security-privacy.md`.

## 4. Gateway design (Python 3.12, Litestar 2.x, uv)

`gateway/app/{config,personality,llm,stt,tts,memory,tools,security,api,audio}/` with tests under
`gateway/tests/`. Single-process async; SQLite via aiosqlite; structured JSON logging.
Weather via Open-Meteo (no API key — verified approach, current-forecast API);
network diagnostics server-side (host facts) + device-reported link stats; speed test explicit, bounded.

## 5. Phases (see roadmap)

P1 face+touch+boot → P2 audio mic/speaker real capture/play → P3 wifi+gateway+auth →
P4 voice loop STT→LLM→TTS → P5 wake-word (honest) → P6 personality/memory/behaviors →
P7 network tools/OTA design → P8 servo-ready interfaces.

## 6. Verification status (as of 2026-10-20)

| Item | Status | Evidence |
|---|---|---|
| Toolchain builds `m5stack-core2` | compile-verified | `pio run -e m5stack-core2` SUCCESS (RAM 0.7%, Flash 23.5%); espressif32@6.13.0 + M5GFX/M5Unified pinned |
| Firmware units (emotion/face/audio/touch/power/tilt/config/app) | compile-verified | integrated build, no device run |
| Gateway API + services | test-verified (dev machine) | pytest; suite green in both dep modes |
| Memory persistence (SQLite via aiosqlite-free stdlib store) | test-verified | persistence across store instances, forget/summary round-trips |
| TTS->STT roundtrip on dev machine | verified | piper en_US-lessac-medium -> faster-whisper base, transcription matched |
| Gateway with no providers configured | verified honest errors | TestClient, no fake replies |
| Wake/name-mode endpoint `/v1/wake` (opt-in) | test-verified | stub STT, 6 unit tests; device chunk streaming pending |
| esp-sr wake-word feasibility | research-verified (source inspection) | docs/wake-word.md |
| Face simulator (browser) | sim-verified | simulator/serve.sh |
| Display/touch/mic/speaker/IMU/power on Core2 | **device-unverified** | no board attached |
| Real end-to-end voice conversation | **device-unverified** | needs device + gateway on network |
| Wake word via real audio | **not implemented**, never claimed | see docs/wake-word.md |

- All API facts above: source-verified (cloned M5Unified/M5GFX/esp-sr master Oct 2026), **device-unverified**.
- No audio/wake/face behavior claimed working on hardware yet.
