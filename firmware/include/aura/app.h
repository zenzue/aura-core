// PetApp: application state machine + event pump (main task).
#pragma once
#include <aura/aura.h>
#include <aura/anim.h>
#include <aura/renderer.h>
#include <aura/hal.h>
#include <aura/events.h>

namespace aura {

enum class AppState : uint8_t { BOOT, DIAGNOSTICS, FACE, PROVISIONING /*Phase3*/, ERROR };

class PetApp {
 public:
  void boot();                 // runs in setup(): inits all subsystems
  void tick();                 // main loop: poll events, update engine+renderer

  // ---- diagnostics harness ----
  void toggleDiagnostics();    // double-tap top-right corner
  bool diagnosticsActive() const { return _state == AppState::DIAGNOSTICS; }

 private:
  void handleEvent(const Event& e);
  void renderDiagnostics();
  void updateProactive(uint32_t now_ms);

  AppState _state = AppState::BOOT;
  DeviceSettings _settings;
  bool _diag_mode = false;
  uint32_t _last_diag_draw = 0;
  uint32_t _last_proactive_check = 0;
  bool _boot_banner_until_set = false;
};

}  // namespace aura
