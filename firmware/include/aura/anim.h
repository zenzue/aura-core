// Emotion engine, easing, expression library and idle behavior scheduler.
// PURE C++ (no M5/Arduino calls except millis() supplied via time source).
#pragma once
#include <aura/aura.h>
#include <functional>

namespace aura {

using NowMsFn = uint32_t (*)();

// ---------- Easing ----------
namespace easing {
float linear(float t);
float easeInOutCubic(float t);
float easeOutBack(float t);
float easeOutElastic(float t);      // damped, clamped t in 0..1
float easeInQuad(float t);
float easeOutQuad(float t);
float easeInOutSine(float t);
}  // namespace easing

// Random helpers shared by engine (xorshift, seeded in begin).
namespace rng {
void seed(uint32_t s);
uint32_t next();                    // raw 32-bit
float uniformf(float lo, float hi);
int uniformi(int lo, int hi);       // inclusive
float nudge(float target, float current, float max_step);
}  // namespace rng

class EmotionEngine {
 public:
  void begin(uint32_t seed_extra = 0);
  // Advance all animation state. now_ms monotonic ms clock. Cheap; never sleeps.
  void update(uint32_t now_ms);

  const FaceRigState& rig() const { return _rig; }
  // Apply theme colors into rig defaults (called once at boot + on settings change).
  void applyTheme(uint16_t bgTop, uint16_t bgBottom, uint16_t core, uint16_t edge, uint16_t accent);

  // ---------- High-level control (thread-safe ONLY from main/app task) ----------
  void setEmotion(Emotion e, float intensity = 1.0f);
  Emotion emotion() const { return _emotion; }
  bool isQuietBehaviorAllowed() const;        // quiet hours gate for proactive speech/anim

  void onTouchLookAt(float x_px, float y_px); // gaze follows touch point
  void onTouchEnd();                           // gaze returns to drift
  void onPet();                                // affection response chain
  void onWakeAck();                            // short excited response (wake reply)
  void onListening(bool active);               // listening expression hold
  void onThinking(bool active);
  void onSpeakingLevel(uint8_t level);         // amplitude-driven speak anim
  void onTilt(float ax, float ay, float az);   // reacts to device tilt (throttled internally)
  void onProactiveNow();                       // behavior engine proactive tick now
  void setSleeping(bool sleeping);             // deep sleep mode vs awake
  void setQuietHours(uint8_t startHour, uint8_t endHour, bool enabled);
  bool sleeping() const { return _sleep_mode; }

  // Diagnostics: cycles through all emotions with dwell.
  void setDiagnosticCycle(bool on, uint32_t dwell_ms = 2500);
  bool currentEmotionListForDiag(Emotion& next_out); // helper used by app

 private:
  FaceRigState _rig {};
  NowMsFn _now = nullptr;
  uint32_t _last_update_ms = 0;
  uint32_t _last_blink_ms = 0;
  uint32_t _next_blink_ms = 0;
  uint32_t _blink_until_ms = 0;
  uint32_t _blink_hold_ms = 0;
  uint8_t _blink_queue = 0;                    // pending extra blinks (double blink)
  uint32_t _next_glance_ms = 0;                // idle gaze wander
  uint32_t _glance_until_ms = 0;
  float _glance_x = 0, _glance_y = 0, _gaze_tx = 0, _gaze_ty = 0;
  bool _touch_look = false;
  float _touch_look_x = 0, _touch_look_y = 0;
  uint32_t _last_react_ms = 0;                 // throttle tilt/pet reactions
  uint32_t _react_until_ms = 0;
  uint32_t _proactive_due_ms = 0;
  uint32_t _sleep_after_idle_ms = 0;           // idle->sleepy timeline
  uint32_t _last_activity_ms = 0;
  bool _sleep_mode = false;
  bool _listening = false;
  bool _thinking = false;
  bool _diag = false, _diag_list_flag = false;
  uint32_t _diag_next_ms = 0;
  Emotion _emotion = Emotion::NEUTRAL;
  float _intensity = 1.0f;
  uint8_t _quiet_start = 22, _quiet_end = 8;   // quiet hours
  bool _quiet_enabled = false;
  uint32_t _quiet_clock_ms = 0;                // reserved: hour applied from app time source
  uint8_t _hour_of_day = 255;                  // set by app via setHourOfDay
  uint8_t _diag_index = 0;
  uint32_t _dwell_ms = 2500;
 public:
  void setHourOfDay(uint8_t h) { _hour_of_day = h; }
  void onActivity() { _last_activity_ms = _rig_activity(); }
  uint32_t _rig_activity() const { return _last_update_ms; }
};

}  // namespace aura
