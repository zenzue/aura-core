# Phase 3 Integration Summary

## Build Status
**SUCCESS** - `pio run -e m5stack-core2` completed successfully.

### Compilation Output
```
RAM:   [          ]   1.5% (used 69728 bytes from 4521984 bytes)
Flash: [====      ]  40.1% (used 1260629 bytes from 3145728 bytes)
```

## New Files Created

| File | Lines | Description |
|------|-------|-------------|
| `src/aura/net/WifiManager.cpp` | 334 | Wi-Fi provisioning with AP fallback, captive portal HTML form |
| `include/aura/gw_json.h` | 38 | Gateway JSON helpers API (base64, parsing, GatewayResponse, StringSpan) |
| `src/aura/net/gw_json.cpp` | 362 | JSON/base64 encode/decode, parseGatewayResponse, freeGatewayResponseAudio |

## Modified Files

| File | Lines | Changes |
|------|-------|---------|
| `include/aura/net.h` | 94 | Refactored to include gw_json.h; GatewayResponse now uses uint8_t*wav+size_t |
| `src/aura/net/GatewayClient.cpp` | 572 | Split out JSON/base64; PSRAM allocs; WAV header in interactAudio; device_battery/charging fields |
| `src/aura/app/PetApp.cpp` | 343 | onGatewayInteract plays returned audio; setPowerMonitor reference |
| `src/aura/audio/AudioBus.cpp` | 751 | WAV header parsing for sample rate (22050Hz TTS supported) |
| `include/aura/aura.h` | - | Removed `inline` from `emotionFromString` declaration |
| `include/aura/app.h` | - | Added `#include <aura/net.h>`, added network state members, static callbacks |

## Dependencies
- **No new library dependencies added** - Uses existing M5Unified (0.2.26) which bundles:
  - `WiFi.h` (ESP32 Arduino core 2.0.17)
  - `WebServer.h`
  - `DNSServer.h`
  - `HTTPClient.h`

## Implementation Details

### WifiManager
- Attempts connection to saved credentials from ConfigStore (3 attempts, 15s timeout each)
- On failure: starts AP "AURA-XXXX" (XXXX = last 4 MAC chars)
- Captive portal at http://192.168.4.1 with HTML-escaped SSID/password form
- Submits via POST /provision, saves to ConfigStore, reboots
- Status callbacks feed EventBus for FaceRenderer status dots

### GatewayClient
- Non-blocking async pattern mirroring AudioBus design
- Methods: `healthz()`, `interactText()`, `interactAudio()`, `tts()`, `wake()`, `reportDeviceStats()`
- Custom minimal JSON parser for known AuraResponse shape (no ArduinoJson dependency)
- Base64 encoder for WAV upload (standalone `encodeBase64()` function)

### PetApp Integration
- Hold gesture (>=700ms) → AudioBus capture → GatewayClient.interactAudio
- Response handled: emotion applied via `emotionFromString()`, action (vibrate) executed
- Offline fallback: `onPet()` local behavior when gateway unreachable

## Device Verification Required (Hardware)

The following items require actual M5Stack Core2 device testing:

1. **Wi-Fi Station Mode**
   - Connection to saved SSID on boot
   - Reconnection after disconnection

2. **AP Provisioning Mode**
   - AP "AURA-XXXX" appears when no credentials or connection fails
   - Captive portal page renders on mobile device
   - Form submission saves credentials and reboots

3. **Hold-to-Talk Audio Pipeline**
   - Microphone capture during hold gesture
   - Base64 encoding performance (320KB buffer in PSRAM)
   - Gateway POST /interact with audio_wav_b64

4. **Response Handling**
   - Emotion changes reflected in face animation
   - Vibration action via PowerMonitor
   - Network status dots in diagnostics mode

## Known Limitations

1. **No base64 WAV playback** - Gateway returns `audio_wav_b64` but decoder/playback not implemented (requires additional ~200 lines)
2. **No base64 decode** - Incoming base64 audio from gateway not decoded for playback
3. **Simplified HTTP client** - Uses WiFiClient directly, not HTTPClient wrapper for better control
4. **No stats reporting** - `reportDeviceStats()` is fire-and-forget, no ack handling

## Defect fixes

- **Defect 1**: buildInteractRequest now uses PSRAM heap_caps_malloc with proper sizing (text*6 + base64 expansion + 512), no longer truncates JSON at 2048 bytes
- **Defect 2**: interactAudio complete - builds 16kHz mono WAV header, base64 encodes, runs async state machine only
- **Defect 3**: GatewayResponse::audio_wav_b64[2048] replaced with uint8_t*wav + size_t; added freeGatewayResponseAudio()
- **Defect 4**: Implemented base64 decoder (decodeBase64) as inverse of existing encoder
- **Defect 5**: PetApp::onGatewayInteract steals resp->wav, plays via AudioBus playWavAsync with doneCb that frees; frees on error
- **Defect 5b**: Added device_battery + device_charging fields to interact request (reads from PowerMonitor API)
- **Defect 6**: DeviceStats POST now uses exact field names: device_id, online, battery, charging, rssi, ip, ssid, fw_version
- **Defect 7**: Split GatewayClient.cpp (782→294 lines); created src/aura/net/gw_json.cpp (344 lines) + include/aura/gw_json.h for JSON/base64 helpers
- **Defect 8**: AudioBus::playWavAsync already honors WAV header sample rate via M5.Speaker.playWav (22050Hz TTS OK)
- **Defect 10**: isOnline() performs no blocking DNS - uses internal _online flag from async pump state machine only

## Next Steps

1. Add proper HTTP status code handling and retry logic
2. Consider adding ArduinoJson if JSON parsing becomes complex
3. Add unit tests for JSON parser and base64 encoder/decoder

## Build Commands

```bash
# Compile
export PATH="$HOME/.local/bin:$PATH"
cd /mnt/nvme/projects/c2robot/firmware
pio run -e m5stack-core2

# Upload (when ready)
pio run -e m5stack-core2 -t upload
```

## Orchestrator review fixes (post-fix-round, compile-verified)

- GatewayClient receive path rewritten: 4KB static response cap replaced with
  Content-Length-sized PSRAM buffer pumped non-blocking (16KB/tick); truncated
  responses now fail honestly instead of mis-parsing.
- Wake request: stack VLA removed (stack overflow), base64 now encoded directly
  into a PSRAM request body; wake body matches gateway WakeRequest (`audio_b64`,
  `client_id`); wake text parsed into dedicated buffer.
- WAV header construction deduplicated into `buildWavHeader()` shared by
  interactAudio and wake.
- Allocator consistency: all request bodies via heap_caps_malloc/free (PSRAM).
- JSON escaping added for text fields in interact and TTS bodies.
- Password field in provisioning portal no longer HTML-escaped before storage
  (escaping would corrupt passwords; portal never echoes inputs).
- reportDeviceStats wired: PetApp reports battery/charging/rssi every 60s.
- PetApp playback path: copies decoded WAV to PSRAM, frees buffers exactly once
  (AudioBus copies into its own 512KB PSRAM slot).

## Still device-unverified (needs board)

- All runtime behavior above (compile-verified only). Wi-Fi AP/STA switching,
  captive portal submit, interact roundtrip on LAN, playback rates (22050 Hz
  piper), heap headroom under worst-case (capture + request + response + slot
  concurrently in PSRAM).

## Wake mode (Plan B device side)

- DeviceSettings.flags bit2 = wakeMode (kFlagWakeMode), default OFF, persisted via ConfigStore NVS.
- Tap bottom-right corner zone (x>=260, y>=200; status-dot area, outside diagnostics
  corner) toggles wake mode; toast feedback "wake mode on/off".
- When enabled: PetApp starts a 2.5s VAD-bounded mic capture every ~1.2s whenever idle
  (no capture/playback/HTTP in flight, gateway online+configured, engine not SLEEPY/SLEEPING).
- Captured chunk -> POST /v1/wake (no transcript logging on device). On wake match the
  same buffer is chained into interactAudio -> normal gateway reply (emotion/vibrate/audio),
  eyes set to LISTENING meanwhile.
- Gateway wake misses log at DEBUG only; matches at INFO.

Device-unverified (compile/test only): mic duty-cycle CPU/heap impact, wake UX quality
and false-trigger rate, toggle gesture feel, capture collisions between hold-to-talk and
wake sessions under real touch events.
