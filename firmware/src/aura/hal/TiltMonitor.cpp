// TiltMonitor: IMU accelerometer monitoring, tilt detection with rate-limiting.
//
// begin(): Initializes IMU, verifies first read is valid.
// update(): Polls every 150ms:
//   - Detects significant acceleration change (>0.35g vector magnitude from last emitted)
//   - Detects orientation flip (az < -0.30g)
//   - Rate-limited to 1200ms minimum between events
//   - Emits IMU_TILT with a=clamp(ax*1000), b=clamp(ay*1000) in milli-g units

#include <aura/hal.h>
#include <aura/events.h>
#include <aura/log.h>
#include <M5Unified.h>
#include <algorithm>

namespace aura {

static inline int16_t clampToInt16(float val) {
  if (val > 32767.0f) return 32767;
  if (val < -32768.0f) return -32768;
  return static_cast<int16_t>(val);
}

class TiltMonitorImpl {
 public:
  bool begin() {
    _healthy = false;
    _lastUpdateMs = 0;
    _lastEventMs = 0;
    _last_ax = 0.0f;
    _last_ay = 0.0f;
    _last_az = 0.0f;

    // IMU is already initialized by M5Unified.begin()
    // Just verify first read is valid
    float ax, ay, az;
    if (M5.Imu.getAccel(&ax, &ay, &az)) {
      // Check if values are reasonable (not NaN or extreme outliers)
      if (std::isfinite(ax) && std::isfinite(ay) && std::isfinite(az)) {
        _healthy = true;
        _last_ax = ax;
        _last_ay = ay;
        _last_az = az;
        AURA_LOGF("TiltMonitor IMU healthy, initial accel=(%.2f, %.2f, %.2f)g", ax, ay, az);
      }
    }

    if (!_healthy) {
      AURA_LOGW("TiltMonitor IMU health check failed");
    }
    return _healthy;
  }

  void update() {
    if (!_healthy) return;

    uint32_t now = millis();
    if (now - _lastUpdateMs < 150) return;  // 150ms poll interval
    _lastUpdateMs = now;

    // Rate limit event emission to 1200ms
    if (now - _lastEventMs < 1200) return;

    float ax, ay, az;
    if (!M5.Imu.getAccel(&ax, &ay, &az)) {
      AURA_LOGW("TiltMonitor IMU read failed");
      _healthy = false;
      return;
    }

    // Check for NaN
    if (!std::isfinite(ax) || !std::isfinite(ay) || !std::isfinite(az)) {
      AURA_LOGW("TiltMonitor IMU read NaN detected");
      _healthy = false;
      return;
    }

    // Calculate vector magnitude change from last emitted
    float dax = ax - _last_ax;
    float day = ay - _last_ay;
    float daz = az - _last_az;
    float deltaMag = std::sqrt(dax*dax + day*day + daz*daz);

    bool emit = false;
    const float kChangeThreshold = 0.35f;  // 0.35g
    const float kFlipThreshold = -0.30f;   // flip when az < -0.30g

    // Significant change
    if (deltaMag > kChangeThreshold) {
      emit = true;
      AURA_LOGF("TiltMonitor tilt: delta=%.2fg (ax=%.2f ay=%.2f az=%.2f)", deltaMag, ax, ay, az);
    }
    // Orientation flip (device upside down)
    else if (az < kFlipThreshold && _last_az >= kFlipThreshold) {
      emit = true;
      AURA_LOGF("TiltMonitor flip: az=%.2f", az);
    }

    if (emit) {
      // Clamp to int16 range (multiply by 1000 for milli-g)
      int16_t ma = clampToInt16(ax * 1000.0f);
      int16_t mb = clampToInt16(ay * 1000.0f);

      Event e{EventKind::IMU_TILT, ma, mb, 0};
      EventBus::instance().post(e);

      _lastEventMs = now;
      // Update last emission values (not last read, for delta calculation)
      _last_ax = ax;
      _last_ay = ay;
      _last_az = az;
    }
  }

  bool healthy() const { return _healthy; }

 private:
  bool _healthy;
  uint32_t _lastUpdateMs;
  uint32_t _lastEventMs;
  float _last_ax, _last_ay, _last_az;
};

static TiltMonitorImpl g_tiltImpl;

bool TiltMonitor::begin() {
  return g_tiltImpl.begin();
}

void TiltMonitor::update() {
  g_tiltImpl.update();
}


}  // namespace aura
