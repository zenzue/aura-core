# AURA — AI Robot Pet & Personal Assistant (M5Stack Core2)

An expressive, original AI companion for the M5Stack Core2 (ESP32): animated face, voice conversation,
AI assistant through a local gateway, pet behaviors, and persistent memory.

> **Status:** under active development. See `docs/roadmap.md` for verified vs planned features.
> Hardware verification is tracked per-feature in `docs/hardware-verification.md`.

## Monorepo layout

```
firmware/    ESP32 Core2 firmware (PlatformIO, C++17, M5Unified/M5GFX)
gateway/     Python AI gateway (Litestar, Gemini/Ollama, Whisper STT, Piper TTS, tools, memory)
simulator/   Desktop/browser face-animation simulator (developer tool)
docs/        architecture, hardware, setup, troubleshooting
scripts/     dev helpers
```

## Quickstart (development machine)

Firmware build (does not require Homebrew):

```bash
python3 -m pip install -U platformio   # or: uv tool install platformio
pio run -e m5stack-core2              # compile
```

Gateway setup (requires Python 3.12+, uv):

```bash
cd gateway
uv sync
cp .env.example .env   # fill in your keys
uv run aura-gateway
```

Full setup guide: `docs/macos-setup.md`.

## License

TBD (target: open source, license to be chosen before release).
