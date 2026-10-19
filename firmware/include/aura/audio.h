// AudioBus: half-duplex mic/speaker owner. Task-safe public API; internals
// run on a dedicated freeRTOS task on core 0. Mic is suspended during playback.
#pragma once
#include <aura/aura.h>

namespace aura {

struct AudioDiagOut {
  bool micBeginOk; bool spkBeginOk; size_t lastCaptureSamples; uint32_t lastRms;
  uint32_t captureDropCount; uint32_t playbackCount; uint32_t errors;
  uint8_t micState;   // 0 off,1 arming,2 capturing
  uint8_t spkState;   // 0 off,1 playing
};

class AudioBus {
 public:
  static AudioBus& instance();
  // init NVS volume, prepare. Does NOT turn mic or speaker on.
  bool init();
  uint8_t volume() const { return _volume; }
  void setVolume(uint8_t v);

  // ---- Mic (half-duplex; fails while playing) ----
  // Arms capture session; fills utterance buffer in PSRAM, ends on silence
  // (kSilenceEndMs) or max length. cb called on audio task when ready
  // (buffer only valid until next call -> consume via queue copy in cb).
  using UtteranceCb = void (*)(void* ctx, const int16_t* pcm16, size_t samples);
  bool startCapture(uint32_t max_ms, void* ctx, UtteranceCb cb);
  void abortCapture();
  bool capturing() const { return _capturing; }

  // ---- Speaker ----
  using DoneCb = void (*)(void* ctx, bool ok);
  // WAV (mono PCM s16, any rate): copies into PSRAM buffer, returns immediately.
  bool playWavAsync(const uint8_t* wav, size_t len, void* ctx, DoneCb cb);
  bool playTone(uint16_t freq_hz, uint16_t ms);
  bool speakBeep();          // short "attention" blip (mic off while playing)
  bool stopPlayback();
  bool speaking() const;
  float lastLevel() const;   // 0..1 RMS proxy of recent playback for animation

  void diagnostics(AudioDiagOut& out);
  uint8_t micStateDbg() const;

 private:
  AudioBus() = default;
  uint8_t _volume = 196;
  volatile bool _capturing = false;
  float _last_level = 0.f;
  AudioDiagOut _diag {};
};

}  // namespace aura
