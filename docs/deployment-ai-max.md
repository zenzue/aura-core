# Deploying AURA on the AI Max machine (Ryzen AI Max, AMD64)

The AI Max serves two roles: a secondary gateway host, and a remote
llama.cpp inference server for the Jetson gateway. There is **no NVIDIA GPU**
here — nothing in the gateway or adapters assumes one.

## 1. Build llama.cpp server (llamacpp provider target)

```bash
sudo apt install -y cmake build-essential git libvulkan-dev
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_VULKAN=ON      # Vulkan offload on Radeon 80M
cmake --build build --config Release -j$(nproc)
```
No Vulkan? build without `-DGGML_VULKAN` (CPU) — same commands.
Verify: `vulkaninfo --summary | head` shows the AMD GPU.

Run (replace with your GGUF):

```bash
build/bin/llama-server -m ~/models/<model>.gguf \
  --host 0.0.0.0 --port 8080 \
  --api-key <optional-token>        # enables bearer auth on llama-server
```
The gateway calls `http://ai-max:8080/v1/models` and
`/v1/chat/completions` — give `LLAMACPP_BASE_URL` either `http://ai-max:8080`
or `.../v1` (never appended twice). With `--api-key` set
`LLAMACPP_AUTH_MODE=bearer` + `LLAMACPP_API_KEY`; without it keep `none`
— the gateway sends no dummy key.

## 2. Gateway on AI Max (Scenario D)

Identical to the Jetson guide except paths/extras: `uv sync` + extras, `.env`
with `AI_PROVIDER=llamacpp`, `LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1`,
local STT/TTS (CPU) work fine — piper and faster-whisper need no GPU.

## 3. Gateway on Jetson pointing here (Scenario B)

On the Jetson `.env`:
`AI_PROVIDER=llamacpp`,
`LLAMACPP_BASE_URL=http://<ai-max-host>:8080/v1`,
`LLAMACPP_MODEL=<exact -s model id reported by /v1/models>`.
Nothing else changes; firmware stays the same image.

## 4. systemd + firewall

```bash
sudo cp /opt/aura-gateway/gateway/deploy/aura-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now aura-gateway
sudo ufw allow in on lo || true
sudo ufw allow from 192.168.0.0/24 to any port 8080 proto tcp   # LAN only
```
llama-server with `--api-key` over LAN HTTP is acceptable inside a trusted
network; for anything crossing untrusted networks terminate TLS via nginx.

## 5. Ollama on AI Max (optional alternative LLM host)

Ollama runs here too (`ollama/ollama` linux AMD64 tarball); set the gateway's
`OLLAMA_BASE_URL` to it. Vulkan support for ollama on AMD is still
experimental — prefer llama.cpp on this machine.
