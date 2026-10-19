// PowerMonitor: battery/charging polling with hysteresis + one-shot vibration task.
// Low battery event at <15%, re-arm above 22%. Charging transitions emit once.
// vibrate() spawns a short FreeRTOS task; never blocks the caller.

#include <aura/hal.h>
#include <aura/events.h>
#include <aura/log.h>
#include <M5Unified.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace aura {

using Charging = m5::Power_Class::is_charging_t;
constexpr Charging kDischarging = m5::Power_Class::is_discharging;
constexpr Charging kCharging = m5::Power_Class::is_charging;

struct VibrateTaskCtx {
  uint8_t level;
  uint32_t ms;
};

static void vibrateTask(void* arg) {
  VibrateTaskCtx* ctx = static_cast<VibrateTaskCtx*>(arg);
  M5.Power.setVibration(ctx->level);
  vTaskDelay(pdMS_TO_TICKS(ctx->ms));
  M5.Power.setVibration(0);
  delete ctx;
  vTaskDelete(nullptr);
}

class PowerMonitorImpl {
 public:
  void begin() {
    _lastUpdateMs = 0;
    _lastBatteryLevel = -1;
    _lowBatteryArmed = false;
    _lastChargingState = getCharging();
    int32_t level = M5.Power.getBatteryLevel();
    _lastBatteryLevel = level;
    if (level >= 0 && level < 15) _lowBatteryArmed = false;
  }

  void update() {
    uint32_t now = millis();
    if (now - _lastUpdateMs < 5000) return;
    _lastUpdateMs = now;

    int32_t level = M5.Power.getBatteryLevel();
    Charging charging = getCharging();

    if (level >= 0) {
      bool isLow = level < 15;
      if (isLow && !_lowBatteryArmed) {
        Event e{EventKind::POWER_LOW, static_cast<int16_t>(level), 0, 0};
        EventBus::instance().post(e);
        AURA_LOGF("POWER_LOW battery=%d%%", static_cast<int>(level));
        _lowBatteryArmed = true;
      } else if (!isLow && level > 22 && _lowBatteryArmed) {
        _lowBatteryArmed = false;
        AURA_LOGF("POWER re-armed battery=%d%%", static_cast<int>(level));
      }
      _lastBatteryLevel = level;
    }

    if (charging != _lastChargingState) {
      if (charging == kCharging) {
        Event e{EventKind::POWER_CHARGING, static_cast<int16_t>(level), 0, 0};
        EventBus::instance().post(e);
        AURA_LOGF("POWER_CHARGING battery=%d%%", static_cast<int>(level));
      }
      _lastChargingState = charging;
    }
  }

  int batteryPercent() {
    int32_t level = M5.Power.getBatteryLevel();
    return level < -1 ? -1 : static_cast<int>(level);
  }

  bool isCharging() { return getCharging() == kCharging; }

  void vibrate(uint8_t level, uint32_t ms) {
    if (level == 0 || ms == 0) return;
    VibrateTaskCtx* ctx = new VibrateTaskCtx{level, ms};
    if (xTaskCreatePinnedToCore(vibrateTask, "vib", 2048, ctx, 2, nullptr, 0) != pdPASS) {
      AURA_LOGW("vibrate task create failed");
      delete ctx;
    }
  }

 private:
  uint32_t _lastUpdateMs = 0;
  int32_t _lastBatteryLevel = -1;
  Charging _lastChargingState = kDischarging;
  bool _lowBatteryArmed = false;

  static Charging getCharging() {
    Charging c = M5.Power.isCharging();
    return c == charge_unknown_bad() ? kDischarging : c;
  }
  static Charging charge_unknown_bad() { return m5::Power_Class::charge_unknown; }
};

static PowerMonitorImpl g_powerImpl;

void PowerMonitor::begin() { g_powerImpl.begin(); }
void PowerMonitor::update() { g_powerImpl.update(); }
int PowerMonitor::batteryPercent() { return g_powerImpl.batteryPercent(); }
bool PowerMonitor::isCharging() { return g_powerImpl.isCharging(); }
void PowerMonitor::vibrate(uint8_t level, uint32_t ms) { g_powerImpl.vibrate(level, ms); }

}  // namespace aura
