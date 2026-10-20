# AURA AI infrastructure: supported deployment scenarios
#
# Core2 ── Wi-Fi ── AURA gateway (Linux ARM64/AMD64) ── LLM provider
# The development Mac (or any dev box) only builds/flashes firmware.
# Gateway, STT, TTS, LLM and inference hosts are all independent.

## Deployment topology rules

1. The gateway is a plain FastAPI-style Python service (Litestar) on any Linux
   box. It runs STT (faster-whisper) and TTS (piper) locally, and reaches LLMs
   over HTTP. It never requires a GPU; when one is present, providers use it.
2. The LLM server may be on the same machine or a different one. Provider
   base URLs are fully configurable (localhost, IPv4, IPv6, LAN hostname,
   FQDN, HTTPS), so "gateway and LLM must be same host" is explicitly NOT a
   deployment assumption anywhere in the code.
3. The Core2 knows exactly three things: its Wi-Fi credentials, the gateway
   URL + port, and its device token. It never carries LLM API keys.

## Accelerator support (detect, never assume)

| Host | Detection | What it enables |
|---|---|---|
| Jetson Orin (JetPack 6) | `nvidia-smi` (Orin nvgpu), `tegrastats` | ollama CUDA/Jetson build, faster-whisper CUDA (optional), piper on CPU fine |
| AI Max (Ryzen AI Max 300-series) | `lspci`/`rocminfo` (no NVIDIA), Vulkan via `vulkaninfo` | llama.cpp Vulkan/HIP offload; ollama vulkan experimental; faster-whisper/piper run CPU-only reliably |
| Any Linux dev box | same checks | nothing required — CPU fallback always works |

Gateway itself is CPU-only; STT/TTS work on every target without accelerators.

## Scenario A — Jetson Orin gateway + Jetson Ollama (fully local, private)

```
Core2 → http://jetson:8765 (gateway + STT + TTS + tools + memory)
gateway → http://127.0.0.1:11434/api/chat (ollama on same Jetson)
```
`.env`: `AI_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`,
`OLLAMA_MODEL=<model loaded on Jetson>`. Nothing leaves the LAN.

## Scenario B — Jetson Orin gateway + remote AI Max llama.cpp (best token throughput)

```
Core2 → http://jetson:8765 (gateway + STT + TTS)
gateway → http://ai-max:8080/v1/chat/completions (llama-server --model ... --port 8080)
```
`.env`: `AI_PROVIDER=llamacpp`,
`LLAMACPP_BASE_URL=http://ai-max.lan:8080/v1` (or `http://192.168.x.x:8080`),
`LLAMACPP_MODEL=<llama-server model ident>`. STT/TTS stay on the Jetson.

## Scenario C — Jetson Orin gateway + Gemini cloud

```
Core2 → http://jetson:8765
gateway → https://generativelanguage.googleapis.com (google-genai SDK)
```
`.env`: `AI_PROVIDER=gemini`, `GEMINI_API_KEY=...`. Cloud calls mean prompts
leave the network — this is the only scenario that does, and failover never
routes local traffic to it unless `ALLOW_CLOUD_FAILOVER=true`.

## Scenario D — AI Max gateway + local llama.cpp

```
Core2 → http://ai-max:8765 (gateway + STT + TTS)
gateway → http://127.0.0.1:8080/v1/chat/completions
```
`.env`: `AI_PROVIDER=llamacpp`, `LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1`.

All four scenarios use the **same Core2 firmware image** — only the gateway
URL/device token on the device differ. Switching scenarios never requires
reflashing beyond the provisioning page change.

## Provider failover across scenarios

Optional, explicit, bounded (`LLM_FAILOVER_CHAIN=ollama,llamacpp`).
Cloud (Gemini) is excluded from the chain unless `ALLOW_CLOUD_FAILOVER=true`,
so a dead local provider never silently forwards private prompts to the cloud.

## Admin / switching without reflashing

`ADMIN_TOKEN` enables `POST /v1/admin/provider` (`{"provider":"ollama"}`) to
switch providers at runtime — the same operation as editing `.env` + restart.
Without `ADMIN_TOKEN`, the admin API returns 403; the device token never
authorizes admin.
