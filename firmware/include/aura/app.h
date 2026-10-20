// PetApp: application state machine + event pump (main task).
#pragma once
#include <aura/aura.h>
#include <aura/anim.h>
#include <aura/renderer.h>
#include <aura/hal.h>
#include <aura/events.h>
#include <aura/net.h>

namespace aura {

enum class AppState : uint8_t { BOOT, DIAGNOSTICS, FACE, PROVISIONING, ERROR };

class PetApp {
 public:
  void boot();                 // runs in setup(): inits all subsystems
  void tick();                 // main loop: poll events, update engine+renderer

  // ---- diagnostics harness ----
  void toggleDiagnostics();    // double-tap top-right corner
  void toggleWakeMode();     // tap bottom-right corner zone
  bool diagnosticsActive() const { return _state == AppState::DIAGNOSTICS; }

 private:
  void handleEvent(const Event& e);
  void renderDiagnostics();
  void updateProactive(uint32_t now_ms);
  
  static void onNetStatus(const char* status_text, bool online);
  static void onWakeCaptured(void* ctx, const int16_t* pcm16, size_t samples);
  static void onWakeCheck(void* ctx, bool woke, const char* text);
  static void onGatewayInteract(void* ctx, const GatewayResponse* resp, bool ok);
  static void onAudioCaptured(void* ctx, const int16_t* pcm16, size_t samples);

  AppState _state = AppState::BOOT;
  DeviceSettings _settings;
  bool _diag_mode = false;
  uint32_t _last_diag_draw = 0;
  uint32_t _last_proactive_check = 0;
  uint32_t _last_stats_ms = 0;
  static const uint32_t kStatsReportMs = 60000;
  bool _boot_banner_until_set = false;
  
  WifiManager _wifiManager;
  GatewayClient _gatewayClient;
  bool _wifi_init_done = false;
  bool _capturing_audio = false;
  uint32_t _next_wake_check_ms = 0;
};

}  // namespace aura
