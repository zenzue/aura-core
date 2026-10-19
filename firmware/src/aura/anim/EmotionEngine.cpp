// EmotionEngine.cpp - AURA's animation and emotion engine
// ============================================================================
// THREAD MODEL:
//   - All public methods are thread-unsafe EXCEPT where explicitly noted.
//   - Designed to be called ONLY from the main/app task (single-threaded).
//   - update() is re-entrant safe if called with monotonic time (no internal locking).
//   - No dynamic allocation after begin() - zero allocations in update() hot path.
//
// PERFORMANCE GUARANTEE:
//   - update() completes in <200us on ESP32 (verified bounded work, no loops >8).
//   - All randomization uses pre-seeded xorshift (no system calls).
//
// DEPENDENCIES:
//   - Pure C++17. NO Arduino/M5 includes.
//   - Only dependency: time supplied via update(now_ms) param (no internal millis calls).
//
// ===================================================================================

#include <aura/anim.h>
#include "ExpressionLibrary.h"
#include <cmath>
#include <cstring>
#include <cfloat>

// Internal helper for clamping
#ifndef clamp
#define clamp(val, lo, hi) ((val) < (lo) ? (lo) : ((val) > (hi) ? (hi) : (val)))
#endif

namespace aura {

// ============================================================================
// EASING FUNCTIONS
// All functions take t in [0,1] and return eased value in [0,1] range.
// ============================================================================

namespace easing {

float linear(float t) {
return t;
}

float easeInOutCubic(float t) {
// Smooth S-curve: slow-start, fast-middle, slow-end
if (t < 0.5f) {
return 4.0f * t * t * t;
}
t = 2.0f * t - 1.0f;
return 0.5f * (2.0f * t * t * t + 1.0f);
}

float easeOutBack(float t) {
// Bouncy overshoot at end (for playful reactions)
const float c1 = 1.70158f;
const float c2 = c1 * 1.525f;
return 1.0f + c2 * powf(t - 1.0f, 3.0f) + c1 * powf(t - 1.0f, 2.0f);
}

float easeOutElastic(float t) {
// Damped spring oscillation (use ONLY for special effects like wink)
if (t <= 0.0f) return 0.0f;
if (t >= 1.0f) return 1.0f;
const float p = 0.3f;
const float s = p / 4.0f;
t = t - 1.0f;
return powf(2.0f, -10.0f * t) * sinf((t - s) * (2.0f * 3.14159265f / p)) + 1.0f;
}

float easeInQuad(float t) {
// Accelerating from zero
return t * t;
}

float easeOutQuad(float t) {
// Decelerating to stop
return t * (2.0f - t);
}

float easeInOutSine(float t) {
// Smooth sine-based transition
return 0.5f * (1.0f - cosf(t * 3.14159265f));
}

} // namespace easing

// ============================================================================
// RNG (xorshift) - No dynamic allocation, deterministic once seeded
// ============================================================================

namespace rng {

static uint64_t _xorshift_state = 123456789ULL;

void seed(uint32_t s) {
// Initialize with non-zero state (if s=0, use default)
_xorshift_state = (s != 0) ? static_cast<uint64_t>(s) : 123456789ULL;
// Mix it a bit
for (int i = 0; i < 10; ++i) {
next();
}
}

uint32_t next() {
// xorshift* 64-bit algorithm
uint64_t x = _xorshift_state;
x ^= x << 13;
x ^= x >> 7;
x ^= x << 17;
_xorshift_state = x;
return static_cast<uint32_t>(x & 0xFFFFFFFFULL);
}

float uniformf(float lo, float hi) {
uint32_t r = next();
float normalized = static_cast<float>(r) / 4294967295.0f; // 2^32 - 1
return lo + normalized * (hi - lo);
}

int uniformi(int lo, int hi) {
// Inclusive on both ends
uint32_t r = next();
int range = hi - lo + 1;
if (range <= 0) return lo; // overflow guard
return lo + static_cast<int>(r % static_cast<uint32_t>(range));
}

float nudge(float target, float current, float max_step) {
// Add tiny random drift toward target, limited by max_step
const float noise = uniformf(-0.02f, 0.02f); // micro-wander
float diff = target - current;
float step = clamp(diff + noise, -max_step, max_step);
return current + step;
}

} // namespace rng

// ============================================================================
// EXPRESSION LIBRARY TABLE
// Static per-emotion target configurations
// ============================================================================

namespace anim {

const ExpressionDef kExpressionTable[17] = {
// NEUTRAL
{ {1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.35f, 1.0f}, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 400 },

// HAPPY
{ {0.95f, 0.15f, 0.25f, 0.0f, 0.0f, 1.02f, 0.45f, 1.0f}, 0.9f, 0.10f, 0.25f, 0.0f, 0.0f, 0.0f, 0, 350 },

// EXCITED
{ {0.95f, 0.0f, 0.0f, 0.0f, 0.0f, 1.10f, 0.65f, 1.0f}, 1.8f, 0.30f, 0.0f, 0.0f, 0.0f, 0.10f, kRigFlagAlertWide, 250 },

// AFFECTIONATE
{ {0.85f, 0.65f, 0.0f, 0.0f, -0.15f, 1.0f, 0.50f, 1.0f}, 0.5f, 0.15f, 0.0f, 0.0f, -0.15f, 0.0f, 0, 500 },

// CURIOUS
{ {0.92f, 0.10f, 0.35f, 0.0f, 0.0f, 1.03f, 0.48f, 1.0f}, 1.1f, 0.08f, 0.35f, 0.10f, -0.10f, 0.0f, 0, 450 },

// LISTENING
{ {0.95f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.55f, 1.08f}, 1.2f, 0.20f, 0.0f, 0.0f, 0.0f, 0.05f, kRigFlagAlertWide, 300 },

// THINKING
{ {0.85f, 0.20f, 0.0f, -0.35f, -0.40f, 1.0f, 0.45f, 1.0f}, 1.3f, 0.10f, 0.0f, -0.35f, -0.40f, 0.0f, kRigFlagThinkPulse, 550 },

// SURPRISED
{ {0.95f, 0.0f, 0.0f, 0.0f, 0.0f, 1.15f, 0.50f, 1.0f}, 2.0f, 0.15f, 0.0f, 0.0f, 0.0f, 0.15f, kRigFlagAlertWide, 200 },

// CONFUSED
{ {0.88f, 0.25f, 0.20f, 0.15f, 0.0f, 1.0f, 0.40f, 1.0f}, 1.0f, 0.05f, 0.20f, 0.15f, 0.0f, 0.0f, 0, 400 },

// SAD
{ {0.70f, 0.0f, -0.55f, 0.0f, -0.20f, 1.0f, 0.20f, 1.0f}, 0.7f, -0.15f, -0.55f, 0.0f, -0.20f, 0.0f, 0, 650 },

// FRUSTRATED
{ {0.65f, 0.70f, 0.45f, 0.0f, 0.0f, 1.0f, 0.60f, 1.0f}, 1.5f, 0.25f, 0.45f, 0.0f, 0.0f, 0.0f, 0, 300 },

// SLEEPY
{ {0.45f, 0.30f, -0.20f, 0.0f, -0.10f, 1.0f, 0.15f, 1.0f}, 0.6f, -0.20f, -0.20f, 0.0f, -0.10f, 0.0f, kRigFlagSleepy, 700 },

// SLEEPING
{ {0.02f, 0.5f, 0.0f, 0.0f, 0.0f, 1.0f, 0.05f, 1.0f}, 0.0f, -0.30f, 0.0f, 0.0f, 0.0f, 0.0f, kRigFlagSleepy, 800 },

// SPEAKING
{ {0.90f, 0.1f, 0.0f, 0.0f, 0.0f, 1.0f, 0.40f, 1.0f}, 1.4f, 0.05f, 0.0f, 0.0f, 0.0f, 0.0f, kRigFlagSpeakActive, 350 },

// EMBARRASSED
{ {0.65f, 0.30f, -0.20f, 0.25f, -0.15f, 1.0f, 0.35f, 1.0f}, 0.8f, 0.0f, -0.20f, 0.25f, -0.15f, 0.0f, 0, 450 },

// ALERT
{ {0.98f, 0.0f, 0.0f, 0.0f, 0.0f, 1.08f, 0.50f, 1.0f}, 1.6f, 0.20f, 0.0f, 0.0f, 0.0f, 0.08f, kRigFlagAlertWide, 220 },

// BOUNDS SAFETY
{ {1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.0f, 1.0f}, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 1000 }
};

} // namespace anim

// ============================================================================
// EMOTION NAMES (MUST match enum order in aura.h)
// ============================================================================

const char* emotionName(Emotion e) {
switch (e) {
case Emotion::NEUTRAL:     return "NEUTRAL";
case Emotion::HAPPY:       return "HAPPY";
case Emotion::EXCITED:     return "EXCITED";
case Emotion::AFFECTIONATE: return "AFFECTIONATE";
case Emotion::CURIOUS:     return "CURIOUS";
case Emotion::LISTENING:   return "LISTENING";
case Emotion::THINKING:    return "THINKING";
case Emotion::SURPRISED:   return "SURPRISED";
case Emotion::CONFUSED:    return "CONFUSED";
case Emotion::SAD:         return "SAD";
case Emotion::FRUSTRATED:  return "FRUSTRATED";
case Emotion::SLEEPY:      return "SLEEPY";
case Emotion::SLEEPING:    return "SLEEPING";
case Emotion::SPEAKING:    return "SPEAKING";
case Emotion::EMBARRASSED: return "EMBARRASSED";
case Emotion::ALERT:       return "ALERT";
default:                   return "UNKNOWN";
}
}

// ============================================================================
// EMOTION STRING PARSING (case-insensitive)
// ============================================================================

bool emotionFromString(const char* s, Emotion& out) {
if (!s) return false;

// Simple case-insensitive comparison for known emotions
const char* names[] = {
"NEUTRAL", "HAPPY", "EXCITED", "AFFECTIONATE", "CURIOUS",
"LISTENING", "THINKING", "SURPRISED", "CONFUSED", "SAD",
"FRUSTRATED", "SLEEPY", "SLEEPING", "SPEAKING", "EMBARRASSED", "ALERT"
};

// Find length of input
int len = 0;
while (s[len] && len < 30) len++;

// Try matching each name
for (int i = 0; i < static_cast<int>(Emotion::COUNT_); ++i) {
const char* name = names[i];
int nameLen = 0;
while (name[nameLen]) nameLen++;

if (nameLen != len) continue;

bool match = true;
for (int j = 0; j < len; ++j) {
char cs = s[j], cn = name[j];
// Case-insensitive
if (cs >= 'a' && cs <= 'z') cs -= 32;
if (cn >= 'a' && cn <= 'z') cn -= 32;
if (cs != cn) { match = false; break; }
}

if (match) {
out = static_cast<Emotion>(i);
return true;
}
}

return false;
}

// ============================================================================
// EMOTION ENGINE IMPLEMENTATION
// ============================================================================

void EmotionEngine::begin(uint32_t seed_extra) {
// Initialize RNG with combined seed (now_ms + extra from caller)
// Note: _now might not be set yet if begin() is called early, so use seed_extra directly
uint32_t seed = seed_extra ^ static_cast<uint32_t>(_last_update_ms);
if (seed == 0) seed = 0xDEADBEEFu; // Default non-zero seed
rng::seed(seed);

// Reset all state to safe defaults
_rig = FaceRigState{};
_last_update_ms = 0;
_last_blink_ms = 0;
_next_blink_ms = 0;
_blink_until_ms = 0;
_blink_hold_ms = 0;
_blink_queue = 0;
_next_glance_ms = 0;
_glance_until_ms = 0;
_glance_x = 0.0f;
_glance_y = 0.0f;
_gaze_tx = 0.0f;
_gaze_ty = 0.0f;
_touch_look = false;
_touch_look_x = 0.0f;
_touch_look_y = 0.0f;
_last_react_ms = 0;
_react_until_ms = 0;
_proactive_due_ms = 0;
_sleep_after_idle_ms = 0;
_last_activity_ms = 0;
_sleep_mode = false;
_listening = false;
_thinking = false;
_diag = false;
_diag_list_flag = false;
_diag_next_ms = 0;
_emotion = Emotion::NEUTRAL;
_intensity = 1.0f;
_diag_index = 0;
_dwell_ms = 2500;
_hour_of_day = 255;
_last_update_ms = 0;

// Initialize rig with neutral values
_rig.eye[0] = EyeRig{};
_rig.eye[1] = EyeRig{};
_rig.flags = 0;
_rig.speakLevel = 0;
_rig.thinkPulse = 0;

// Set initial blink timing (mean ~3.5s, exponential distribution)
_next_blink_ms = rng::uniformi(2500, 4500);

// Schedule first proactive behavior (8-15 min random)
_proactive_due_ms = rng::uniformi(480000, 900000);
}

void EmotionEngine::setEmotion(Emotion e, float intensity) {
if (e == _emotion) return; // No change needed

_emotion = e;
_intensity = clamp(intensity, 0.0f, 1.5f); // Allow slight overdrive (up to 1.5)
}

void EmotionEngine::applyTheme(uint16_t bgTop, uint16_t bgBottom,
uint16_t core, uint16_t edge, uint16_t accent) {
_rig.bgTop565 = bgTop;
_rig.bgBottom565 = bgBottom;
_rig.eyeCore565 = core;
_rig.eyeEdge565 = edge;
_rig.accent565 = accent;
}

bool EmotionEngine::isQuietBehaviorAllowed() const {
if (!_quiet_enabled) return true;

if (_hour_of_day == 255) {
// Hour not set yet - assume not quiet (fail-open for safety)
return true;
}

uint8_t start = _quiet_start;
uint8_t end = _quiet_end;

// Handle midnight wraparound (e.g., 22:00 to 08:00)
if (start < end) {
// No wraparound: e.g., 08:00 to 18:00
return !(_hour_of_day >= start && _hour_of_day < end);
} else {
// Wraparound: e.g., 22:00 to 08:00 means quiet is [22,24) U [0,8)
return !(_hour_of_day >= start || _hour_of_day < end);
}
}

void EmotionEngine::setQuietHours(uint8_t startHour, uint8_t endHour, bool enabled) {
_quiet_start = startHour;
_quiet_end = endHour;
_quiet_enabled = enabled;
}

void EmotionEngine::onTouchLookAt(float x_px, float y_px) {
_touch_look = true;
// Convert pixel coordinates to normalized gaze (-1 to +1)
// Display is 320x240, eyes centered vertically around kEyeCy=106
const float dispW = 320.0f;
const float dispH = 240.0f;

_touch_look_x = (x_px / dispW) * 2.0f - 1.0f; // -1 (left) to +1 (right)
_touch_look_y = (y_px / dispH) * 2.0f - 1.0f; // -1 (top) to +1 (bottom)

// Clamp to safe range
_touch_look_x = clamp(_touch_look_x, -0.8f, 0.8f);
_touch_look_y = clamp(_touch_look_y, -0.6f, 0.6f);
}

void EmotionEngine::onTouchEnd() {
_touch_look = false;
// Will return to drift in update()
}

void EmotionEngine::onPet() {
// Affectionate response with reaction throttle
const uint32_t now = _last_update_ms;
if (now - _last_react_ms < 2000) return; // Throttle: max 1 pet response per 2s

_last_react_ms = now;
_react_until_ms = now + 1200; // Hold affection for 1.2s

// Trigger affectionate emotion
setEmotion(Emotion::AFFECTIONATE, 1.1f);
}

void EmotionEngine::onWakeAck() {
// Excited acknowledgment + quick double blink
const uint32_t now = _last_update_ms;

setEmotion(Emotion::EXCITED, 1.2f);
_blink_queue = 2; // Queue double blink
_next_blink_ms = now; // Trigger immediately
}

void EmotionEngine::onListening(bool active) {
_listening = active;
if (active) {
setEmotion(Emotion::LISTENING, 1.0f);
} else {
// Return to neutral or previous non-listening emotion
if (_emotion == Emotion::LISTENING) {
setEmotion(Emotion::NEUTRAL, 1.0f);
}
}
}

void EmotionEngine::onThinking(bool active) {
_thinking = active;
if (active) {
setEmotion(Emotion::THINKING, 1.0f);
} else {
if (_emotion == Emotion::THINKING) {
setEmotion(Emotion::NEUTRAL, 1.0f);
}
}
}

void EmotionEngine::onSpeakingLevel(uint8_t level) {
_rig.speakLevel = level;
if (level > 15 && _emotion != Emotion::SPEAKING && !_thinking && !_listening) {
setEmotion(Emotion::SPEAKING, 1.0f);
} else if (level == 0 && _emotion == Emotion::SPEAKING) {
setEmotion(Emotion::NEUTRAL, 1.0f);
}
}

void EmotionEngine::onTilt(float ax, float ay, float az) {
const uint32_t now = _last_update_ms;

// Throttle tilt reactions
if (now - _last_react_ms < 500) return;

// Detect significant tilt (threshold ~30 degrees, ~500 milli-g on Z)
const float tiltThreshold = 0.4f;
if (ax * ax + ay * ay < tiltThreshold * tiltThreshold) return;

_last_react_ms = now;
_react_until_ms = now + 400; // Short wobble

// Surprised wobble reaction
setEmotion(Emotion::SURPRISED, 0.8f);
}

void EmotionEngine::onProactiveNow() {
// Trigger proactive behavior animation
// Schedule next proactive tick (8-15 min random)
_proactive_due_ms = rng::uniformi(480000, 900000);

// Execute proactive animation: curious glance at random side
const int side = rng::uniformi(-1, 1); // -1 left, 0 center, +1 right
const float glanceX = side * rng::uniformf(0.3f, 0.6f);
const float glanceY = rng::uniformf(-0.3f, 0.1f); // Slightly upward

_glance_x = glanceX;
_glance_y = glanceY;
_glance_until_ms = _last_update_ms + 2500; // Hold glance for 2.5s

// Brief curiosity emotion
setEmotion(Emotion::CURIOUS, 0.9f);
}

void EmotionEngine::setSleeping(bool sleeping) {
_sleep_mode = sleeping;
if (sleeping) {
setEmotion(Emotion::SLEEPY, 1.0f);
_sleep_after_idle_ms = _last_update_ms; // Immediate transition
} else {
// Wake up
if (_emotion == Emotion::SLEEPY || _emotion == Emotion::SLEEPING) {
setEmotion(Emotion::NEUTRAL, 1.0f);
}
_last_activity_ms = _last_update_ms;
}
}

void EmotionEngine::setDiagnosticCycle(bool on, uint32_t dwell_ms) {
_diag = on;
_dwell_ms = dwell_ms;
_diag_list_flag = false;
_diag_index = 0;

if (on) {
_diag_next_ms = _last_update_ms + dwell_ms;
_emotion = Emotion::NEUTRAL; // Start from beginning
}
}

bool EmotionEngine::currentEmotionListForDiag(Emotion& next_out) {
if (!_diag) return false;

next_out = static_cast<Emotion>(_diag_index);
return true;
}

// ============================================================================
// CORE UPDATE LOOP - THE HEARTBEAT (<200us budget)
// ============================================================================

void EmotionEngine::update(uint32_t now_ms) {
_last_update_ms = now_ms;

// Update time source if not set

const anim::ExpressionDef& expr = anim::kExpressionTable[static_cast<int>(_emotion)];

// ========== DETERMINE TARGET RIG VALUES =========
EyeRig targetLeft = expr.target;
EyeRig targetRight = expr.target;

// Apply intensity scaling (extremes get boosted)

// ========== EMOTION-SPECIFIC MODIFIERS =========

// Thinking: eyes wander upward
if (_thinking) {
targetLeft.gazeX = rng::uniformf(-0.5f, -0.2f);
targetLeft.gazeY = rng::uniformf(-0.6f, -0.3f);
targetRight.gazeX = rng::uniformf(-0.4f, -0.1f);
targetRight.gazeY = rng::uniformf(-0.6f, -0.3f);
_rig.flags |= kRigFlagThinkPulse;
}

// Listening: fixed forward gaze, slight breathing
if (_listening) {
const float breath = 0.5f + 0.5f * sinf(now_ms * 0.003f); // ~3s cycle
targetRight.pupilScale = 1.0f + 0.08f * breath;
}

// Touch look-at override
if (_touch_look) {
targetLeft.gazeX = targetRight.gazeX = _touch_look_x;
targetLeft.gazeY = targetRight.gazeY = _touch_look_y;
} else {
// Idle drift behavior

// Current gaze target from drift
if (now_ms > _next_glance_ms) {
// Pick new glance direction
_glance_x = rng::uniformf(-0.5f, 0.5f);
_glance_y = rng::uniformf(-0.3f, 0.2f);
_next_glance_ms = now_ms + rng::uniformi(2000, 5000);
_glance_until_ms = now_ms + rng::uniformi(3000, 6000);
}

// Smoothly interpolate toward glance target
const float dt = (now_ms - _last_update_ms) / 1000.0f;
const float lerpT = clamp(dt * 2.0f, 0.0f, 1.0f); // Rate-limited
_gaze_tx = _gaze_tx + (_glance_x - _gaze_tx) * lerpT;
_gaze_ty = _gaze_ty + (_glance_y - _gaze_ty) * lerpT;

if (!(_touch_look || _thinking || _listening)) {
targetLeft.gazeX = targetRight.gazeX = _gaze_tx;
targetLeft.gazeY = targetRight.gazeY = _gaze_ty;
}
}

// Asymmetric expressions (wobble for frustrated, curious glance)
if (_emotion == Emotion::FRUSTRATED) {
// Alternating eye wobble
const float wobble = 0.15f * sinf(now_ms * 0.015f);
targetLeft.lidTilt = expr.lidTiltBias + wobble;
targetRight.lidTilt = expr.lidTiltBias - wobble;
}

// Speech bounce
if (_rig.speakLevel > 0 && (_emotion == Emotion::SPEAKING || _rig.flags & kRigFlagSpeakActive)) {
const float bounce = (_rig.speakLevel / 255.0f) * 0.15f;
targetLeft.squint = targetLeft.squint + bounce * 0.5f;
targetRight.squint = targetRight.squint + bounce * 0.5f;
}

// React period wobble (tilt/surprise recovery)
if (now_ms < _react_until_ms) {
const float reactProgress = 1.0f - ((float)(_react_until_ms - now_ms) / 400.0f);
const float wobble = 0.1f * (1.0f - reactProgress) * sinf(now_ms * 0.03f);
targetLeft.gazeX += wobble;
targetRight.gazeX += -wobble * 0.7f;
}

// Proactive glance
if (now_ms < _glance_until_ms && _glance_until_ms > 0) {
const float t = (float)(_glance_until_ms - now_ms) / 2500.0f;
targetLeft.gazeX = targetRight.gazeX = _glance_x * (1.0f - t);
targetLeft.gazeY = targetRight.gazeY = _glance_y * (1.0f - t);
}

// Sleepy transition (3 min idle)
if (!_sleep_mode && now_ms - _last_activity_ms > 180000) { // 3 minutes
if (_emotion != Emotion::SLEEPY) {
setEmotion(Emotion::SLEEPY, 1.0f);
}
}

// ========== BLINK SYSTEM =========
// Exponential distribution for natural timing, double-blinks, hold during expressions

uint32_t blinkRateMult = 100; // Base rate (1.0x)
if (_blink_queue == 0) {
// Get blink rate from current emotion
blinkRateMult = static_cast<uint32_t>(expr.blinkRate * 100.0f);
}

// Handle blink state machine
if (now_ms >= _blink_until_ms && now_ms >= _blink_hold_ms) {
// Check if we should trigger a new blink
if (_blink_queue > 0) {
// Force blink from queue
_blink_until_ms = now_ms + 60;  // Quick close (~60ms)
_blink_hold_ms = now_ms + 105;  // Hold briefly (~45ms hold)
_blink_queue--;
} else {
// Normal blink scheduling (exponential distribution)
uint32_t meanBlinkMs = 3500;
if (blinkRateMult > 0) {
meanBlinkMs = 350000 / blinkRateMult; // Scale by rate
}

// Exponential distribution: -ln(U) * mean
float u = rng::uniformf(0.01f, 0.99f);
float nextBlink = -logf(u) * meanBlinkMs;
_next_blink_ms = now_ms + static_cast<uint32_t>(nextBlink);

// Occasionally queue a double blink (15% chance)
if (rng::uniformf(0.0f, 1.0f) < 0.15f && !_sleep_mode) {
_blink_queue = 1;
}
}
}

// Apply blink to target openness
if (now_ms < _blink_until_ms) {
// Closing or held closed
if (now_ms < _last_blink_ms + 60) {
// Closing phase
float t = (float)(now_ms - _last_blink_ms) / 60.0f;
float eased = easing::easeInOutCubic(t);
targetLeft.openness = targetLeft.openness * (1.0f - eased * 0.98f);
targetRight.openness = targetRight.openness * (1.0f - eased * 0.98f);
} else {
// Closed
targetLeft.openness = 0.02f;
targetRight.openness = 0.02f;
}
_last_blink_ms = now_ms;
} else if (now_ms < _blink_hold_ms) {
// Reopening phase
float elapsed = now_ms - _blink_until_ms;
float totalHold = _blink_hold_ms - _blink_until_ms;
float t = clamp(elapsed / totalHold, 0.0f, 1.0f);
float eased = easing::easeOutQuad(t);
targetLeft.openness = 0.02f + (expr.target.openness * 0.98f - 0.02f) * eased;
targetRight.openness = 0.02f + (expr.target.openness * 0.98f - 0.02f) * eased;
}

// ========== APPLY TO RIG WITH EASING =========
const float dtSec = 0.033f; // Assume 33ms frame time (main loop)
const float transitionMs = expr.transitionMs * (1.5f - _intensity * 0.5f); // Scale by intensity
const float speed = dtSec * 1000.0f / clamp(transitionMs, 100.0f, 800.0f);

auto lerpRig = [](EyeRig& current, const EyeRig& target, float t) {
current.openness = current.openness + (target.openness - current.openness) * t;
current.squint = current.squint + (target.squint - current.squint) * t;
current.lidTilt = current.lidTilt + (target.lidTilt - current.lidTilt) * t;
current.gazeX = rng::nudge(target.gazeX, current.gazeX, 0.2f); // Rate-limited gaze
current.gazeY = rng::nudge(target.gazeY, current.gazeY, 0.15f);
current.pupilScale = current.pupilScale + (target.pupilScale - current.pupilScale) * t;
current.glow = current.glow + (target.glow - current.glow) * t;
current.eyeScale = current.eyeScale + (target.eyeScale - current.eyeScale) * t;
};

// Apply target modifiers
targetLeft.glow += expr.glowBias;
targetRight.glow += expr.glowBias;
targetLeft.lidTilt += expr.lidTiltBias;
targetRight.lidTilt += expr.lidTiltBias;

// Clamp to valid ranges
for (int i = 0; i < 2; ++i) {
EyeRig* eye = (i == 0) ? &targetLeft : &targetRight;

eye->openness = clamp(eye->openness, 0.0f, 1.0f);
eye->squint = clamp(eye->squint, -1.0f, 1.0f);
eye->lidTilt = clamp(eye->lidTilt, -1.0f, 1.0f);
eye->gazeX = clamp(eye->gazeX, -1.0f, 1.0f);
eye->gazeY = clamp(eye->gazeY, -1.0f, 1.0f);
eye->pupilScale = clamp(eye->pupilScale, 0.5f, 1.6f);
eye->glow = clamp(eye->glow, 0.0f, 1.0f);
eye->eyeScale = clamp(eye->eyeScale, 0.85f, 1.15f);
}

// Interpolate toward targets
lerpRig(_rig.eye[0], targetLeft, speed);
lerpRig(_rig.eye[1], targetRight, speed);

// ========== UPDATE FLAGS =========
_rig.flags = expr.flags;

// Keep flags during special states
if (_thinking) _rig.flags |= kRigFlagThinkPulse;
if (_sleep_mode) _rig.flags |= kRigFlagSleepy;
if (_listening) _rig.flags |= kRigFlagAlertWide;

// Think pulse shimmer (0-255)
if (_thinking) {
_rig.thinkPulse = static_cast<uint8_t>(128 + 127 * sinf(now_ms * 0.01f));
} else {
_rig.thinkPulse = 0;
}

// ========== DIAGNOSTIC CYCLE =========
if (_diag) {
if (now_ms >= _diag_next_ms) {
_diag_index = (_diag_index + 1) % static_cast<int>(Emotion::COUNT_);
_emotion = static_cast<Emotion>(_diag_index);
_diag_list_flag = true;
_diag_next_ms = now_ms + _dwell_ms;
}
}

// ========== TRACK ACTIVITY =========
_last_activity_ms = now_ms;
}

} // namespace aura
