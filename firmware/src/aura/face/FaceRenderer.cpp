#include <M5Unified.h>
#include "aura/renderer.h"
#include "aura/log.h"

namespace aura {

static inline uint16_t blend565(uint16_t c0, uint16_t c1, float t) {
    uint8_t r0 = (c0 >> 11) & 0x1F;
    uint8_t g0 = (c0 >> 5) & 0x3F;
    uint8_t b0 = c0 & 0x1F;
    uint8_t r1 = (c1 >> 11) & 0x1F;
    uint8_t g1 = (c1 >> 5) & 0x3F;
    uint8_t b1 = c1 & 0x1F;
    
    int ir = r0 + (r1 - r0) * t;
    int ig = g0 + (g1 - g0) * t;
    int ib = b0 + (b1 - b0) * t;
    
    return rgb565(ir, ig, ib);
}

static inline uint16_t darken565(uint16_t c, float factor) {
    uint8_t r = (c >> 11) & 0x1F;
    uint8_t g = (c >> 5) & 0x3F;
    uint8_t b = c & 0x1F;
    int dr = r * factor;
    int dg = g * factor;
    int db = b * factor;
    return rgb565(dr, dg, db);
}

static inline uint16_t brighten565(uint16_t c, float factor) {
    uint8_t r = (c >> 11) & 0x1F;
    uint8_t g = (c >> 5) & 0x3F;
    uint8_t b = c & 0x1F;
    int br = r + (31 - r) * factor;
    int bg = g + (63 - g) * factor;
    int bb = b + (31 - b) * factor;
    return rgb565(br, bg, bb);
}

void FaceRenderer::begin(uint8_t brightness) {
    setBrightness(brightness);
    
    // Initial background fill
    drawBackground(kDefaultBgTop565, kDefaultBgBottom565);
    _fps_last_ms = millis();
    _fps_frames = 0;
    
#if AURA_LOG_LEVEL >= 1
    AURA_LOGF("FaceRenderer::begin() brightness=%u", brightness);
#endif
}

void FaceRenderer::setBrightness(uint8_t b) {
    M5.Display.setBrightness(b);
    _last_brightness = b;
}

void FaceRenderer::drawBackground(uint16_t top565, uint16_t bottom565) {
    _last_bg_top = top565;
    _last_bg_bot = bottom565;
    
    M5.Display.startWrite();
    for (int y = 0; y < 240; y++) {
        float t = (float)y / 239.0f;
        uint16_t color = blend565(top565, bottom565, t);
        M5.Display.fillRect(0, y, 320, 1, color);
    }
    
    M5.Display.endWrite();
    _have_bg = true;
}

void FaceRenderer::fillEyeRegion(int idx, uint16_t bgApprox) {
    // Dirty region: eye center ± (halfW*1.18*1.15 + margin + glow buffer)
    const int cx = kEyeCx[idx];
    const int cy = kEyeCy;
    const float fullW = kEyeHalfW * 1.18f * 1.15f;
    const int maxRadius = (int)(fullW * 2.4f) + kRegionMargin + 8;  // +8 for glow halo
    
    int x0 = cx - maxRadius;
    int y0 = cy - maxRadius;
    int x1 = cx + maxRadius;
    int y1 = cy + maxRadius;
    
    // Clamp to screen
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= 320) x1 = 319;
    if (y1 >= 240) y1 = 239;
    
    int w = x1 - x0 + 1;
    
    // Repaint region with vertical band blend (approximate gradient)
    // Draw 24 vertical bands interpolating bgTop->bgBottom per row within region
    M5.Display.startWrite();
    for (int by = y0; by <= y1; by++) {
        // Find local t within full screen height
        float t = (float)by / 239.0f;
        uint16_t color = blend565(_last_bg_top, _last_bg_bot, t);
        M5.Display.fillRect(x0, by, w, 1, color);
    }
    M5.Display.endWrite();
}

void FaceRenderer::drawEye(int idx, const EyeRig& eye, const FaceRigState& rig) {
    M5.Display.startWrite();
    const int cx = kEyeCx[idx];
    const int cy = kEyeCy;
    float scale = eye.eyeScale;
    float openness = eye.openness;
    float squint = eye.squint;
    float lidTilt = eye.lidTilt;
    float gazeX = eye.gazeX;
    float gazeY = eye.gazeY;
    float pupilScale = eye.pupilScale;
    float glow = eye.glow;
    float speakLevel = (float)rig.speakLevel / 255.0f;
    bool isThinking = (rig.flags & kRigFlagThinkPulse) != 0;
    
    float bounce = speakLevel * 0.04f;
    openness += bounce;
    if (openness > 1.0f) openness = 1.0f;
    
    float travelW = kEyeHalfW * (1.0f - pupilScale * 0.3f) - 2.0f;
    float travelH = kEyeHalfH * 0.8f - 2.0f;
    int pupilXOff = (int)(gazeX * travelW);
    int pupilYOff = (int)(gazeY * travelH);
    
    if (speakLevel > 0.1f) {
        int jitter = (int)(speakLevel * 1.5f);
        pupilXOff += (jitter % 3) - 1;
        pupilYOff += (jitter % 3) - 1;
    }
    
    float eyeW = kEyeHalfW * 2.0f * scale * (1.0f + 0.05f * (squint > 0 ? squint : 0));
    float eyeH = kEyeHalfH * openness * 2.0f * scale;
    
    if (openness < 0.06f) {
        int lineW = (int)(kEyeHalfW * 2.4f * scale);
        int lineWidth = 2 + (int)(eye.glow * 3);
        M5.Display.startWrite();
        M5.Display.fillRect(cx - lineW/2, cy - lineWidth/2, lineW, lineWidth, rig.eyeEdge565);
        M5.Display.endWrite();
        
        // Restore region and return
        fillEyeRegion(idx, rig.bgTop565);
        M5.Display.startWrite();
        M5.Display.fillRect(cx - lineW/2, cy - lineWidth/2, lineW, lineWidth, rig.eyeEdge565);
        M5.Display.endWrite();
        return;
    }
    
    // Handle lid tilt via asymmetric radii (sad droop vs angry rise)
    // Split into top and bottom halves with different corner radii
    
    float innerHalfH = kEyeHalfH * openness * scale;
    
    // ====================
    // (A) GLOW HALO (3 concentric rings)
    // ====================
    int haloBaseR = (int)(innerHalfH * 2.4f);
    int ringStep = 6;
    uint16_t haloColors[3];
    haloColors[0] = blend565(rig.eyeEdge565, blend565(rig.bgTop565, rig.bgBottom565, 0.5f), glow * 0.20f);
    haloColors[1] = blend565(rig.eyeEdge565, blend565(rig.bgTop565, rig.bgBottom565, 0.5f), glow * 0.12f);
    haloColors[2] = blend565(rig.eyeEdge565, blend565(rig.bgTop565, rig.bgBottom565, 0.5f), glow * 0.06f);
    
    for (int i = 0; i < 3; i++) {
        int r = haloBaseR - i * ringStep;
        if (r > 4) {
            M5.Display.fillSmoothCircle(cx, cy, r, haloColors[i]);
        }
    }
    
    int eyeWInt = (int)eyeW;
    int eyeHInt = (int)eyeH;
    int eyeRadius = eyeWInt / 4;
    if (eyeRadius < 6) eyeRadius = 6;
    
    // Apply tilt by offsetting top/bottom
    int topY = cy - eyeHInt / 2;
    int topH = eyeHInt / 2;
    int bottomH = eyeHInt - topH;
    
    int topRadius = eyeRadius;
    int bottomRadius = eyeRadius;
    if (lidTilt < 0) {
        bottomRadius = (int)(eyeRadius * (1.0f + lidTilt * 0.3f));
    } else {
    }
    
    // Draw bottom half first
    M5.Display.fillSmoothRoundRect(cx - eyeWInt/2, cy - eyeHInt/4, eyeWInt, bottomH, bottomRadius, rig.eyeEdge565);
    // Draw top half
    M5.Display.fillSmoothRoundRect(cx - eyeWInt/2, topY, eyeWInt, topH, topRadius, rig.eyeEdge565);
    
    // ====================
    float irisR = innerHalfH * 0.65f * pupilScale;
    float coreR = innerHalfH * 0.40f * pupilScale;
    int irisRInt = (int)irisR;
    int coreRInt = (int)coreR;
    if (irisRInt < 2) irisRInt = 2;
    if (coreRInt < 1) coreRInt = 1;
    
    uint16_t irisColor = blend565(rig.eyeEdge565, rig.eyeCore565, 0.4f);
    M5.Display.fillSmoothCircle(cx + pupilXOff, cy + pupilYOff, irisRInt, irisColor);
    
    uint16_t coreColor = brighten565(rig.eyeCore565, glow * 0.3f);
    if (isThinking && (millis() % 200) < 100) {
        coreColor = blend565(coreColor, rig.accent565, rig.thinkPulse / 255.0f * 0.4f);
    }
    M5.Display.fillSmoothCircle(cx + pupilXOff, cy + pupilYOff, coreRInt, coreColor);
    
    float pupilR = coreR * 0.55f;
    int pupilRInt = (int)pupilR;
    if (pupilRInt < 1) pupilRInt = 1;
    
    uint16_t pupilColor = rgb565(2, 6, 16);
    M5.Display.fillSmoothCircle(cx + pupilXOff, cy + pupilYOff, pupilRInt, pupilColor);
    
    float hlR = coreR * 0.35f;
    int hlRInt = (int)hlR;
    if (hlRInt < 1) hlRInt = 1;
    
    int hlXOff = (int)(-pupilR * 0.6f);
    int hlYOff = (int)(-pupilR * 0.6f);
    
    uint16_t hlColor = brighten565(rig.eyeCore565, 0.85f);
    M5.Display.fillSmoothCircle(cx + pupilXOff + hlXOff, cy + pupilYOff + hlYOff, hlRInt, hlColor);
    
    M5.Display.endWrite();
}

void FaceRenderer::render(const FaceRigState& rig) {
    uint32_t now = millis();
    _fps_frames++;
    
    if (now - _fps_last_ms >= 1000) {
        _fps = (float)_fps_frames * 1000.0f / (now - _fps_last_ms);
        _fps_frames = 0;
        _fps_last_ms = now;
    }
    
    auto q = [](float v) { int i = (int)(v * 16.0f); if (i > 16) i = 16; if (i < -16) i = -16; return i; };
    
    M5.Display.startWrite();
    
    for (int i = 0; i < 2; i++) {
        const EyeRig& e = rig.eye[i];
        const int oq = q(e.openness), gxq = q(e.gazeX), gyq = q(e.gazeY), glq = q(e.glow);
        const float ok = e.eyeScale + e.pupilScale * 0.1f;
        auto& c = _eye_cache[i];
        if (c.openness_q != oq || c.gx_q != gxq || c.gy_q != gyq ||
            c.extra_q != glq || fabsf(c.other_key - ok) > 0.02f) {
            fillEyeRegion(i, rig.bgTop565);
            drawEye(i, e, rig);
            c.openness_q = oq; c.gx_q = gxq; c.gy_q = gyq; c.extra_q = glq; c.other_key = ok;
        }
    }
    
    M5.Display.endWrite();
    
    if (rig.flags & kRigFlagShowStatus) {
        drawStatusDots(
            (rig.flags & 0x10) != 0,
            true,
            rig.flags & kRigFlagShowStatus
        );
    }
}

void FaceRenderer::drawStatusDots(bool wifiUp, bool gatewayOk, bool micListening) {
    uint8_t newBits = (wifiUp ? 0x01 : 0) | (gatewayOk ? 0x02 : 0) | (micListening ? 0x04 : 0);
    if (newBits == _last_status_bits) return;
    _last_status_bits = newBits;
    
    M5.Display.startWrite();
    
    int startX = 290;
    int y = kBottomY - 8;
    uint16_t dimColor = darken565(kDefaultAccent565, 0.4f);
    
    int x = startX;
    if (wifiUp) {
        M5.Display.fillCircle(x, y, 3, kDefaultAccent565);
    } else {
        M5.Display.fillCircle(x, y, 3, dimColor);
    }
    x -= 18;
    
    if (gatewayOk) {
        M5.Display.fillCircle(x, y, 3, kDefaultEyeEdge565);
    } else {
        M5.Display.fillCircle(x, y, 3, dimColor);
    }
    x -= 18;
    
    if (micListening) {
        M5.Display.fillCircle(x, y, 3, 0x07FF);
    } else {
        M5.Display.fillCircle(x, y, 3, dimColor);
    }
    
    M5.Display.endWrite();
}

void FaceRenderer::status(bool wifiUp, bool gatewayOk, bool micListening) {
    drawStatusDots(wifiUp, gatewayOk, micListening);
}

void FaceRenderer::toast(const char* text, uint16_t color565) {
    M5.Display.startWrite();
    
    if (strlen(_last_toast) > 0) {
        int w = strlen(_last_toast) * 6 + 16;
        int h = 12;
        int x = (320 - w) / 2;
        int y = kBottomY - 20;
        
        float t = (float)y / 239.0f;
        uint16_t bgCol = blend565(_last_bg_top, _last_bg_bot, t);
        M5.Display.fillRect(x, y, w, h, bgCol);
    }
    
    if (text == nullptr || strlen(text) == 0) {
        _last_toast[0] = '\0';
        M5.Display.endWrite();
        return;
    }
    
    strncpy(_last_toast, text, sizeof(_last_toast) - 1);
    _last_toast[sizeof(_last_toast) - 1] = '\0';
    
    M5.Display.setTextFont(1);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(color565);
    
    int textW = strlen(text) * 6;
    int x = (320 - textW) / 2;
    int y = kBottomY - 16;
    
    M5.Display.setCursor(x, y);
    M5.Display.printf("%s", text);
    
    M5.Display.endWrite();
}

void FaceRenderer::banner(const char* text, uint16_t fg565) {
    M5.Display.startWrite();
    
    M5.Display.fillScreen(_last_bg_top);
    
    M5.Display.setTextFont(1);
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(fg565);
    M5.Display.setTextDatum(MC_DATUM);
    
    M5.Display.drawString(text, 160, 120);
    
    M5.Display.endWrite();
}

}  // namespace aura
