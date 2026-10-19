# Hardware verification status

Date: 2026-10-20. Honest split between what is VERIFIED on a development machine and
what remains UNVERIFIED because no ESP32 board is attached.

## Verified on development machine (Linux aarch64)

| Item | Evidence | Date |
|---|---|---|
| Toolchain builds firmware for m5stack-core2 | `pio run -e m5stack-core2` -> SUCCESS; RAM 0.7% (33,196 B), Flash 23.5% (737,905 B) | 2026-10-20 |
| Gateway core (config/schemas/app/api) | pytest `tests_core`: green | 2026-10-20 |
| Gateway services (audio/tools/memory) | pytest full suite: 84 passed | 2026-10-20 |
| Voice roundtrip (TTS->STT) on dev machine | Piper `en_US-lessac-medium` synthesized speech transcribed correctly by faster-whisper `base` | 2026-10-20 |
| Gateway with no LLM provider configured | returns clear error (`AI service unavailable`), never fake text (TestClient) | 2026-10-20 |
| esp-sr wake-word capabilities | source inspection of esp-sr master + Kconfig gates (docs/wake-word.md) | 2026-10-20 |

## NOT verified (no hardware attached)

Nothing in the firmware has been run on a device yet. Specifically UNVERIFIED:

1. Display: M5GFX init on ILI9342C, rotation, brightness, tearing, face render speed.
2. Touch: `Touch.getDetail()` mapping, hold-gesture timing, tap zones.
3. Microphone: PDM capture via M5Unified `M5.Mic` at 16kHz mono on Core2
   (data GPIO34 / clock GPIO0; mic and MAX98357A speaker share I2S0).
4. Speaker: MAX98357A class-D output through AudioBus half-duplex switching;
   vibration motor playback.
5. IMU: MPU6885 tilt detection and wake-on-motion.
6. Power: AXP192 charge/percentage/battery-read and idle-sleep policy.
7. NVS persistence of volume/settings.
8. Wi-Fi provisioning + real gateway HTTP roundtrip from device.
9. End-to-end voice conversation on the pet: mic -> WAV -> gateway -> LLM -> TTS -> speaker.
10. Wake word in real audio (never claimed working; see docs/wake-word.md).

## How to verify (device procedure)

1. Install platformio CLI (done: pio 6.6.9 via uv tool on this machine).
2. Attach Core2 via USB; confirm serial device appears (`pio device list`).
3. `pio run -e m5stack-core2 -t upload` (m5stack-core2 env uses `--before default_reset
   --after hard_reset`, 1500000 baud).
4. Serial monitor: `pio device monitor -b 115200` and run through docs/roadmap.md tests.
5. Gateway on the same network: run `python -m app.main` from gateway/ (after
   `uv sync --all-extras`), then point firmware `gateway_base_url` at the machine.
6. Test matrix: face animations at 60fps, blink/speak/mood changes, touch tap/hold,
   mic capture level, TTS playback, tilt reactions, charging/power events, NVS
   persistence across reboot, Wi-Fi provisioning from AP mode.

## Development-machine-only facts used by this repo

- Display geometry (320x240, ILI9342C 320x240 via SPI) and eye centers (104/216, y=106,
  halfW=34, halfH=40) are taken from M5GFX/M5Unified defaults for Core2 - consistent
  with M5Stack documentation, but the on-screen result is unverified without hardware.
- Audio sample rates (mic 16kHz, TTS 22.05kHz piper) match component specs; device-side
  resample/throughput unverified.
- RAM/flash numbers are from the toolchain linker, not runtime heap. Heap usage on
  device (especially AudioBus WAV buffers: capture ~2s*16k*2B ~64KB peak, playback
  decode buffers) is a known risk - documented in roadmap.md performance phase.

## Test matrix detail (run on device)

1. Boot banner + face: background gradient renders, eyes appear centered, no flicker.
2. Emotions: cycle all 16 via gateway-less serial test; check blink cadence changes.
3. Touch: tap left/right halves, top; hold >= 700ms triggers talk mode; double tap.
4. Audio: capture 2s on hold-release; serial logs show RMS; play WAV back; vibration pulses.
5. Tilt: tilt > 30 deg within 1s produces curious/listening reaction (untested).
6. Power: charger plug/unplug logs; idle after 5 min, face dims.
7. Gateway roundtrip: hold-to-talk question -> TTS reply audible within ~5s on Wi-Fi.
8. Reboot persistence: volume + settings restored from NVS.
