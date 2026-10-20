# AURA — AI Robot Pet & Personal Assistant (M5Stack Core2)

An expressive, original AI companion for the M5Stack Core2 (ESP32): animated face, voice conversation,
AI assistant through a local gateway, pet behaviors, and persistent memory.

> **Status:** under active development. See `docs/roadmap.md` for verified vs planned features.
> Hardware verification is tracked per-feature in `docs/hardware-verification.md`.

## Monorepo layout

```
firmware/    ESP32 Core2 firmware (PlatformIO, C++17, M5Unified/M5GFX)
gateway/     Python AI gateway (Litestar, Gemini/Ollama/llama.cpp, Whisper STT, Piper TTS, tools, memory)
simulator/   Desktop/browser face-animation simulator (developer tool)
docs/        architecture, hardware, deployment, ai-infrastructure, troubleshooting
scripts/     dev helpers
```

## Architecture in one paragraph

Core2 (face + half-duplex voice + touch behaviors) → Wi-Fi → **AURA gateway**
on any Linux ARM64/AMD64 host (primary: Jetson Orin, secondary: AI Max) →
provider (`gemini` | `ollama` | `llamacpp`) → structured emotional reply →
TTS → speaker + synchronized face. Gateway and LLM server may be different
machines; the Mac is only used for firmware builds/flashing. Deployment
scenarios A–D: `docs/ai-infrastructure.md`.

## Quickstart

Firmware build (any dev box with PlatformIO):

```bash
python3 -m pip install -U platformio   # or: uv tool install platformio
pio run -e m5stack-core2               # compile
```

Gateway on Jetson Orin / AI Max (Python 3.12+, uv):

```bash
cd gateway
uv sync --all-extras
cp .env.example .env   # set AI_PROVIDER + provider URL/model + tokens
uv run aura-gateway    # or: systemd unit in deploy/aura-gateway.service
```

Environment-specific guides: `docs/deployment-jetson-orin.md`,
`docs/deployment-ai-max.md`. Diagnostics: `docs/troubleshooting.md`.

## License

TBD (target: open source, license to be chosen before release).
