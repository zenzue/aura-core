// FaceRenderer: draws FaceRigState onto the Core2 display (M5GFX).
// Partial redraw only: background drawn on demand, per-eye regions on change.
#pragma once
#include <aura/aura.h>

namespace aura {

class FaceRenderer {
 public:
  // init display, draw full background once
  void begin(uint8_t brightness);
  // Draw the face from rig state; only repaint changed regions.
  void render(const FaceRigState& rig);
  // Redraw the background gradient (boot, resize, theme change).
  void drawBackground(uint16_t top565, uint16_t bottom565);
  // Minimal status dots (wifi/net/mic) bottom-right; only on change.
  void status(bool wifiUp, bool gatewayOk, bool micListening);
  // Small transient text toast (status lines). Pass nullptr/"" to clear.
  void toast(const char* text, uint16_t color565 = kDefaultAccent565);
  // Full-screen mode for diagnostics: draw centered text large (boot banner).
  void banner(const char* text, uint16_t fg565);
  // Brightness
  void setBrightness(uint8_t b);
  // Frame timing diagnostic (internal fps meter, -1 if unused)
  float lastFps() const { return _fps; }

 private:
  uint16_t _last_bg_top = 0, _last_bg_bot = 0;
  bool _have_bg = false;
  // per-eye cached key for skip-if-unchanged
  struct EyeCache { int openness_q : 9; int gx_q : 9; int gy_q : 9; int extra_q : 9; float other_key; };
  EyeCache _eye_cache[2];
  uint8_t _last_status_bits = 0xFF;
  char _last_toast[40] = {0};
  uint8_t _last_brightness = 255;
  float _fps = -1.f;
  uint32_t _fps_last_ms = 0;
  uint32_t _fps_frames = 0;

  // internals implemented in .cpp
  void drawEye(int idx, const EyeRig& eye, const FaceRigState& rig);
  void fillEyeRegion(int idx, uint16_t bgApprox);
  void drawStatusDots(bool wifiUp, bool gatewayOk, bool micListening);
};

}  // namespace aura
