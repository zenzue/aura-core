# AURA diagnostics & troubleshooting

## Device shows OFFLINE / gateway unreachable

1. `GET http://<gateway>:8765/healthz` from a laptop on the same LAN.
2. Provisioning page: gateway host/port correct? Gateway host must be
   reachable *by name from the Core2* — mDNS (`jetson.local`) works only
   with responders; prefer static IP or DNS entry.
3. DNS/Gateway latency and RSSI live on the device network diagnostics
   screen; RSSI ≠ internet speed.

## Gateway starts but AI replies fail

`GET /v1/status` → `llm` block names the provider and problem:

| llm block | cause | fix |
|---|---|---|
| `{"provider":"disabled","problems":[...]}` | active provider incomplete (missing key/model/URL) | fix `.env` |
| `healthy:false` + connection refused | provider host down / wrong host:port | check provider machine, base URL |
| `reason: ... 401/403` | `*_AUTH_MODE=bearer` misconfig | set key on both ends |
| `healthy:false` on llamacpp with wrong model | configured `LLAMACPP_MODEL` absent from `/v1/models` | use the exact id llama-server reports |
| ollama `model not present in /api/tags` | model not pulled on remote host | `ollama pull <model>` on provider host |

## Audio pipeline

- Interact with `tts=true` returns no audio → `/v1/status` shows tts
  `disabled` → voice path missing: set `TTS_VOICE_PATH` to a real
  `.onnx` file (download per README).
- faster-whisper import errors → re-run `uv sync --extra whisper` (PyAV/matching
  FFmpeg bundled by faster-whisper 1.2+).

## Provider failover surprises

- Chain entries referencing gemini are ignored unless
  `ALLOW_CLOUD_FAILOVER=true` (logged at warning). This is intentional: local
  prompts never leak to cloud silently.
- Switching via `POST /v1/admin/provider` returns 403 when `ADMIN_TOKEN` is
  empty — by design, admin API is disabled without it.

## Diagnostics tools (ask the pet)

- `get_gateway_health` — uptime + last device stats seen.
- `get_ai_provider_status` — active provider, health, capabilities.
- `get_network_status` — DNS/gateway latency measured honestly (bounded
  throughput test only when asked explicitly).

## Live integration tests

With reachable services set `AURA_LIVE_OLLAMA_URL` + `AURA_LIVE_OLLAMA_MODEL`
(or LLAMACPP/GEMINI equivalents) then
`uv run pytest -m integration`. Without them the tests skip — never pretend
they ran.
