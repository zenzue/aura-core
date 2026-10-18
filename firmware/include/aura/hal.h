// HAL: touch input mapping, power monitor, tilt monitor, NVS config store.
#pragma once
#include <aura/aura.h>
#include <esp_err.h>

namespace aura {

class TouchInput {
 public:
  void begin();                       // hold threshold 700ms etc
  // Polls M5.Touch; pushes EventKind events onto the bus (tap/pet/down/hold...)
  void update();
};

class PowerMonitor {
 public:
  void begin();
  void update();                      // debounced power events (LOW/CHARGING)
  int batteryPercent();
  bool isCharging();
  void vibrate(uint8_t level, uint32_t ms);  // level 1..255; auto-stop
};

class TiltMonitor {
 public:
  bool begin();
  void update();                      // emits IMU_TILT on significant change (throttled)
  bool healthy() const { return _healthy; }
 private:
  bool _healthy = false;
  float _last_ax = 0, _last_ay = 0, _last_az = 0;
  uint32_t _last_ms = 0;
};

struct DeviceSettings {
  char petName[24] = "AURA";
  char gatewayUrl[64] = "";
  char wifiSsid[33] = "";
  char wifiPass[65] = "";
  uint8_t volume = 196;
  uint8_t brightness = 180;
  uint8_t quietStart = 22;
  uint8_t quietEnd = 8;
  uint32_t flags = 0;                 // bit0 quietEnabled, bit1 diagCycle, ...
};

class ConfigStore {
 public:
  bool load(DeviceSettings& s);
  bool save(const DeviceSettings& s);   // nvs commit
  bool factoryWipe();
};

}  // namespace aura
