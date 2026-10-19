# AURA roadmap (after current integration)

## Now / next (ordered)

1. Device bring-up: flash firmware, run the hardware test matrix in
   docs/hardware-verification.md. Expect fixes in display/touch/audio drivers.
2. Gateway wake-detection endpoint (Plan B in docs/wake-word.md): VAD-gated
   mic streaming from device + gateway ASR name-match. Opt-in UI flag + LED/face
   listening indicator.
3. Wi-Fi provisioning on device (AP mode fallback + saved credentials in NVS/ConfigStore).
4. Gateway HTTP client on device: /v1/interact, /v1/tts, /v1/stt, /v1/healthz;
   reconnect/backoff; devstats reporting (battery/tilt/wifi RSSI) from device_status
   (RSSI only; no fabricated speed claims).
5. Face polish: idle expression drift, saccade model, transition presets (blink
   microexpression on emotion change), status dot styling.
6. Audio pipeline on device: capture VAD framing, gateway STT, TTS playback queue,
   barge-in (mic pause while playing), AEC absent - half-duplex constraints documented.
7. Memory: move in-memory store to SQLite (single-user, privacy: add retention +
   forget UI).
8. Performance/heap audit: AudioBus buffer sizing vs display/face cache; measure heap
   minimum on device during worst-case (hold-to-talk -> play TTS with status dots).
9. Tools: real weather/ time (already), speedtest via gateway with honest measurement;
   remove or hide `server_monitor` on single-user home setup.
10. Personality presets + expression presets packaging; config UI (gateway web or
    JSON file + docs).
11. Multi-user/memory scoping if more than one pet or household member; gateway auth.
12. Tests: device-side capture fixture tests on dev machine (feed recorded WAVs
    through gateway AudioBus decode path), CI job running gateway pytest.

## Explicitly out of scope (unless reopened)

- On-device English MultiNet commands (not supported on original ESP32 - see
  docs/wake-word.md).
- Custom "AURA" on-device wake word without paid Espressif training.
- Battery/runtime optimization beyond safe idle/sleep states.
- Cloud accounts, multi-device mesh, OTA fleet management.
