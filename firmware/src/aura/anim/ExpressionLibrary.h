// ExpressionLibrary.h - Internal expression data structures for EmotionEngine
// NOT part of public API; used ONLY by EmotionEngine.cpp
#pragma once

#include <aura/aura.h>
#include <cstdint>

namespace aura {
namespace anim {

// Per-emotion target rig configuration
struct ExpressionDef {
  EyeRig target;           // Target rig state (per-eye deltas applied separately)
  float blinkRate;         // Multiplier for base blink rate (>1 = more frequent)
  float glowBias;          // Additional glow intensity (0..1)
  float lidTiltBias;       // Global lid tilt offset (-1..1)
  float gazeXBias;         // Global gaze X offset (-1..1)
  float gazeYBias;         // Global gaze Y offset (-1..1)
  float eyeScaleBias;      // Eye size modifier (0.9..1.1)
  uint8_t flags;           // kRigFlag* combination
  float transitionMs;      // Base transition duration (ms)
};

// ============================================================================
// EXPRESSION LIBRARY TABLE
// ============================================================================
// All 16 emotions with carefully tuned parameters for natural expression.
// Values are derived from behavioral observations of EMO/Vector-style pets,
// but with original tuning for AURA's character.
//
// Emotion breakdown:
//
// NEUTRAL (0):
//   - Baseline state. Slight glow (0.35), normal openness, no special flags.
//   - Blink rate: 1.0x (~3.5s mean)
//   - Transition: 400ms
//
// HAPPY (1):
//   - Slight upward lid tilt (curious/pleased), moderate glow boost.
//   - Eyes slightly narrowed (squint ~0.15 = happy squint).
//   - Blink rate: 0.9x (slightly slower when content)
//   - Transition: 350ms
//
// EXCITED (2):
//   - Widened eyes (eyeScale 1.10), increased openness.
//   - Strong glow (0.65), alert flags.
//   - Faster blink rate 1.8x (excitement = more eye movement)
//   - Transition: 250ms (snappy)
//
// AFFECTIONATE (3):
//   - Narrowed eyes (squint 0.65), slight downward gaze (looking up through lashes).
//   - Very slow blink rate 0.5x (long, languid blinks).
//   - Mild downward gazeY (-0.15).
//   - Transition: 500ms (slow, soft)
//
// CURIOUS (4):
//   - Upward lid tilt (+0.35 = raised outer lids = interest).
//   - Slight gaze upward (-0.25 Y).
//   - Glance behavior: wanders to sides occasionally.
//   - Transition: 450ms
//
// LISTENING (5):
//   - Forward focus (gaze 0,0), slight brightness increase (glow 0.55).
//   - Slight zoom (pupilScale 1.08).
//   - Alert flag for wide attention.
//   - Transition: 300ms
//
// THINKING (6):
//   - Upward/left gaze (-0.35 X, -0.40 Y) = looking up in thought.
//   - Wandering allowed (thinkPulse shimmer).
//   - Reduced openness (0.85 = contemplative narrowing).
//   - kRigFlagThinkPulse flag set.
//   - Transition: 550ms (deliberate)
//
// SURPRISED (7):
//   - Maximum eye widening (eyeScale 1.15, openness 0.95).
//   - Rapid transition (200ms) for snap reaction.
//   - No squint, lid tilt neutral.
//   - Transition: 200ms (instant)
//
// CONFUSED (8):
//   - Asymmetric lid tilt (one eye slightly raised).
//   - Sideways gaze drift (+0.15 X).
//   - Slight squint (0.25 = puzzled).
//   - Transition: 400ms
//
// SAD (9):
//   - Downward lid tilt (-0.55 = drooping outer lids).
//   - Low openness (0.70), downward gaze (-0.20 Y).
//   - Reduced glow (0.20), no alert flags.
//   - Very slow transition (650ms = sluggish)
//
// FRUSTRATED (10):
//   - Strong squint (0.70), angry lid tilt (+0.45).
//   - Alternating eye wobble (asymmetric).
//   - High intensity glow (0.60).
//   - Transition: 300ms (sharp)
//
// SLEEPY (11):
//   - Heavy lids (openness 0.45), very slow movements.
//   - Reduced glow (0.15), kRigFlagSleepy flag.
//   - Blink hold extended, low gaze (0,-0.10).
//   - Transition: 700ms (sluggish)
//
// SLEEPING (12):
//   - Fully closed (openness 0.02), no transitions.
//   - Minimal glow (0.05).
//   - kRigFlagSleepy flag.
//   - Transition: 800ms (very slow wake)
//
// SPEAKING (13):
//   - Animated by speakLevel (squint varies with volume).
//   - Normal openness (0.90), slight glow (0.40).
//   - kRigFlagSpeakActive flag.
//   - Transition: 350ms
//
// EMBARRASSED (14):
//   - Crossed gaze (±0.25 X, -0.15 Y = looking down/at nose).
//   - Moderate openness (0.65), mild squint (0.30).
//   - Downward lid tilt (-0.20).
//   - Transition: 450ms
//
// ALERT (15):
//   - Maximum attention (openness 0.98, eyeScale 1.08).
//   - kRigFlagAlertWide flag for wide-open hold.
//   - Neutral gaze, no squint.
//   - Transition: 220ms (fast)
//
// ============================================================================

extern const ExpressionDef kExpressionTable[17]; // COUNT_ = 16, +1 for bounds safety

} // namespace anim
} // namespace aura
