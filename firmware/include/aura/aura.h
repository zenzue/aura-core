// AURA core types, constants and shared data contracts.
// Pure C++17, no Arduino/M5 dependencies here (safe for simulator/tests).
#pragma once
#include <cstdint>
#include <cstddef>

namespace aura {

// ---------- Display layout (rotated landscape 320x240) ----------
constexpr int kDisplayW = 320;
constexpr int kDisplayH = 240;
constexpr int kEyeCx[2]  = {104, 216};   // eye box centers
constexpr int kEyeCy     = 106;
constexpr float kEyeHalfW = 34.0f;       // half-width of open eye
constexpr float kEyeHalfH = 40.0f;       // half-height fully open
constexpr int kRegionMargin = 26;        // per-eye dirty region padding
constexpr int kBottomY = 226;            // status strip below this line

// ---------- Emotions (device-side validated set) ----------
enum class Emotion : uint8_t {
  NEUTRAL = 0, HAPPY, EXCITED, AFFECTIONATE, CURIOUS, LISTENING, THINKING,
  SURPRISED, CONFUSED, SAD, FRUSTRATED, SLEEPY, SLEEPING, SPEAKING,
  EMBARRASSED, ALERT, COUNT_
};
inline bool emotionFromString(const char* s, Emotion& out); // impl in EmotionEngine.cpp

const char* emotionName(Emotion e);

// ---------- Face rig ----------
struct EyeRig {
  float openness = 1.0f;    // 1 open .. 0 closed (blink/lids)
  float squint   = 0.0f;    // -1 widened .. +1 narrowed lids
  float lidTilt  = 0.0f;    // -1 sad (outer droop) .. +1 angry/curious (outer rise)
  float gazeX    = 0.0f;    // normalized pupil offset -1..1 within travel area
  float gazeY    = 0.0f;
  float pupilScale = 1.0f;  // 0.5..1.6
  float glow     = 0.35f;   // emissive intensity 0..1
  float eyeScale = 1.0f;    // whole-eye size multiplier 0.85..1.15
};

constexpr uint8_t kRigFlagThinkPulse   = 1 << 0; // eyes wander while thinking
constexpr uint8_t kRigFlagSleepy       = 1 << 1; // heavy lids, slow motion
constexpr uint8_t kRigFlagSpeakActive  = 1 << 2; // mouth/eye bounce from speakLevel
constexpr uint8_t kRigFlagAlertWide    = 1 << 3; // wide-open hold
constexpr uint8_t kRigFlagShowStatus   = 1 << 4; // draw minimal status dots

// ---------- Theme defaults (declared before rig state uses them) ----------
constexpr uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
  return uint16_t(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}
constexpr uint16_t kDefaultBgTop565     = rgb565(4, 10, 24);
constexpr uint16_t kDefaultBgBottom565  = rgb565(10, 22, 40);
constexpr uint16_t kDefaultEyeCore565   = rgb565(150, 255, 250);
constexpr uint16_t kDefaultEyeEdge565   = rgb565(30, 200, 220);
constexpr uint16_t kDefaultAccent565    = rgb565(140, 245, 210);

struct FaceRigState {
  EyeRig eye[2];                    // [0]=left eye (screen left), [1]=right
  uint8_t flags = 0;
  uint8_t speakLevel = 0;           // 0..255 audio amplitude for speaking anim
  uint8_t thinkPulse = 0;           // 0..255 thinking shimmer
  uint8_t blinkShade = 0;           // reserved (lid shading strength)
  // Theme (RGB565). Filled from ThemeStore.
  uint16_t bgTop565 = kDefaultBgTop565;
  uint16_t bgBottom565 = kDefaultBgBottom565;
  uint16_t eyeCore565 = kDefaultEyeCore565;   // iris core
  uint16_t eyeEdge565 = kDefaultEyeEdge565;   // iris rim/glow base
  uint16_t accent565 = kDefaultAccent565;     // secondary accent
};

// ---------- Theme ----------
// ---------- Events ----------
enum class EventKind : uint8_t {
  NONE = 0,
  TOUCH_TAP,            // single tap (a,b = x,y)
  TOUCH_PET,            // repeated tapping = petting (a,b = x,y)
  TOUCH_DOWN,           // press began (a,b = x,y)
  TOUCH_UP,             // press ended (a,b = x,y) duration_ms param
  TOUCH_HOLD_BEGIN,     // hold >= 700ms => push-to-talk begin (a,b = x,y)
  TOUCH_HOLD_END,       // release after hold
  PTT_BEGIN,            // physical long press (BtnPWR) start
  PTT_END,              // physical button release (param = hold_ms)
  AUDIO_UTTERANCE_READY,// captured audio available (param = bytes)
  AUDIO_SPEAK_BEGIN,
  AUDIO_SPEAK_DONE,     // param ok
  AUDIO_ERROR,
  EMOTION_REQUEST,      // param = Emotion
  NET_ONLINE,
  NET_OFFLINE,
  GATEWAY_REACHABLE,
  GATEWAY_LOST,
  IMU_TILT,             // a,b = ax_milli, ay_milli
  POWER_LOW,
  POWER_CHARGING,
  BEHAVIOR_PROACTIVE,   // behavior engine wants attention
  DIAG_PING,
  MAX_,
};

constexpr size_t kEventQueueLen = 16;

// ---------- Audio ----------
constexpr uint32_t kMicSampleRate = 16000;
constexpr uint32_t kMaxUtteranceMs = 10000;
constexpr uint32_t kMinUtteranceMs = 300;
constexpr uint32_t kSilenceEndMs = 900;       // end utterance after silence
constexpr size_t kMaxUtteranceSamples = kMicSampleRate * kMaxUtteranceMs / 1000;

// ---------- Config keys (NVS namespaced "aura") ----------
namespace cfgkeys {
  constexpr const char* NS = "aura";
  constexpr const char* PET_NAME = "pet_name";
  constexpr const char* VOLUME = "vol";
  constexpr const char* BRIGHTNESS = "bright";
  constexpr const char* GATEWAY_URL = "gw_url";
  constexpr const char* DEV_TOKEN = "token";
  constexpr const char* WIFI_SSID = "ssid";
  constexpr const char* WIFI_PASS = "pass";
  constexpr const char* QUIET_START = "q_start";
  constexpr const char* QUIET_END = "q_end";
  constexpr const char* FLAGS = "flags";
}

}  // namespace aura
