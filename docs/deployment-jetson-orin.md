# Deploying AURA gateway on NVIDIA Jetson Orin (JetPack 6, ARM64)

Primary deployment target. The gateway runs independently of any developer
machine; the Mac is only for building/flashing firmware.

## 1. Prerequisites (as root or with sudo)

```bash
sudo apt update && sudo apt install -y build-essential curl git
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs to ~/.local/bin
```

Check accelerators (never assumed):

```bash
nvidia-smi --query-gpu=name --format=csv   # Orin nvgpu present on Jetson
python3 -c "import torch" 2>/dev/null || echo "torch absent - fine, CPU path works"
```

## 2. Gateway (native uv)

```bash
sudo mkdir -p /opt/aura-gateway && sudo chown "$USER" /opt/aura-gateway
git clone <repo-url> /opt/aura-gateway   # or rsync the repo
cd /opt/aura-gateway/gateway
uv sync                    # core deps
uv sync --all-extras       # + google-genai / faster-whisper / piper
cp .env.example .env       # then edit: AI_PROVIDER, model names, tokens
```

Set in `.env` for **Scenario A** (local Ollama):
`AI_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`,
`OLLAMA_MODEL=<your model>`. STT/TTS run locally (Scenario A/C/D identical).

Download the piper voice once:

```bash
uv run --extra piper python -m piper.download_voices --download-dir ./voices en_US-lessac-medium
```
(`TTS_VOICE_PATH=./voices/en_US-lessac-medium.onnx`)

## 3. systemd service

```bash
sudo cp deploy/aura-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aura-gateway
journalctl -u aura-gateway -f
```
Health: `curl -s localhost:8765/healthz`; readiness: `/readyz`;
providers: `/v1/status`.

## 4. Ollama on Jetson (Scenario A)

Install the Jetson/CUDA build of Ollama (see ollama docs for JetPack), then
`ollama pull <model>`. Verify from the gateway host:
`curl -s localhost:11434/api/tags`. Set `OLLAMA_BASE_URL` accordingly.

## 5. Docker (optional)

```bash
cd gateway
docker compose --profile ollama up -d --build
```
Scenario B/D: remove/ignore the ollama service and point
`LLAMACPP_BASE_URL` at the remote llama-server.

## 6. Device-side configuration (same firmware for every scenario)

Provisioning page → gateway host `jetson-host.lan` (or IP), port 8765, device
token. That is the only device change required across all scenarios.

## Security notes

LAN HTTP is development-friendly; for production put TLS in front
(`TLS_VERIFY_OUTBOUND=true` stays, reverse-proxy the gateway with HTTPS and
enable `DEVICE_AUTH_TOKEN`+`ADMIN_TOKEN`). LLM keys live only in `.env`.
