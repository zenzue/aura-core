# AURA Wake-Word Strategy (Core2 = original ESP32)

Research date: 2026-10-20. Verified by cloning esp-sr master (v2.6.x, /tmp/opencode/esp-sr)
and reading its Kconfig.projbuild, lib/ targets and release notes, plus Espressif docs.

## Verified facts (esp-sr source inspection)

1. esp-sr requires ESP-IDF 5.x. Our firmware baseline is arduino-esp32 core 2.0.17
   (IDF 4.4), which CANNOT run esp-sr v2.x as-is. esp-sr v2.6.0 is the first version
   (released ~2026-10-09) to explicitly run on classic ESP32.
2. Classic ESP32 supported wake-word models in esp-sr master: WakeNet9s/10s menu has NO
   target gate (wn9s_hilexin "Hi 乐鑫", wn9s_hiesp "Hi ESP", wn9s_hijason "Hi Jason",
   wn10s_hilexin). WakeNet9/WakeNet10 full models are gated to ESP32-S3/P4/S31.
3. MultiNet (voice command recognition): classic ESP32 gets mn2_cn ONLY (Chinese
   commands). English MultiNet (mn5q8_en/mn6_en/mn7_en) is gated to S3/P4/P4/S31/P4.
   Therefore an English on-device "voice command" vocabulary is NOT available on
   original ESP32.
4. There is NO free local pipeline to train a custom wake word like "AURA" for any
   target. Espressif's official path is a PAID customization service
   (email sales@espressif.com; one-time fee, no per-device fee):
   (a) TTS-only samples, (b) Espressif crowdsourced ~500-speaker corpus + TTS,
   (c) customer corpus >= 20,000 qualified samples (>500 speakers incl >=100 children).
   Community reports (esp-sr issue #88) suggest TTS-trained custom models are possible
   but unproven and unsupported.
5. Practical consequence: on ORIGINAL ESP32 Core2 the only realistic wake words are
   Espressif's pre-trained ones ("Hi ESP", "Alexa"-class on S3/P4 etc.), custom
   "AURA" requires the paid service or an S3-class chip (Core2 is ESP32, not S3).

## Options considered

- Plan A (shipped in firmware now): touch-to-talk. Hold the screen >= 700ms to talk.
  No wake word. Deterministic, private, works today once hardware is verified.
- Plan B (gateway-side detection): device streams VAD-gated mic chunks to gateway;
  gateway runs faster-whisper on chunks and treats any transcript matching a name
  (regex on "aura"/"aura robot") as a wake event. Runs the existing gateway
  faster-whisper; opt-in, latency ~0.3-1s on a laptop-class CPU. Device code exists
  as capture plumbing; gateway wake-detection endpoint is NOT implemented yet.
- Plan C (firmware upgrade, experimental): port firmware to arduino core 3.x (IDF 5.x)
  and use esp-sr WakeNet10s on classic ESP32 with "Hi ESP" (wn9s_hiesp/wn10s_hiesp) as
  the wake word, not "AURA". High effort (core migration), on-device verification
  needed. MultiNet still Chinese-only on classic ESP32.
- Plan D (hardware change): Core2Cloud/Core2ForAgent variants, or the S3-based
  M5Stack "CoreS3"/"Cardputer" lines, unlock WakeNet9 English words (Alexa, Jarvis,
  Computer...) and English MultiNet commands; custom "AURA" still paid-only.

## Recommendation

- Ship Plan A now (already implemented in TouchInput/AudioBus: hold-to-talk).
- Implement Plan B as the first wake mode: opt-in "name mode" that streams
  VAD segments to the gateway and wakes on ASR hit of "aura". Honest label: this is
  ASR keyword spotting, not an on-device wake engine.
- Keep Plan C open: worth doing only after the device is flashed and stable; treat
  as upgrade path to IDF5 + esp-sr for future S3 hardware.
- Do NOT advertise "AURA wake word" on device until either paid Espressif training or
  real audio verification exists. Project rule: wake-word is not complete until a
  real audio trigger is verified.

## Status

- [x] esp-sr master inspection (Kconfig gates, lib targets) - done 2026-10-20
- [x] Espressif customization process verified (paid fee, corpus sizes) - done 2026-10-20
- [x] Plan A touch-to-talk implemented (firmware compiles; hardware unverified)
- [ ] Plan B gateway wake-detection - not implemented
- [ ] Plan C IDF5 migration - not started
- [ ] Real-audio verification on device - needs hardware
