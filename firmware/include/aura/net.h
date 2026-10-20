// net.h - Network stack: Wi-Fi provisioning + gateway HTTP client
#pragma once

#include <aura/aura.h>
#include <aura/events.h>
#include <aura/gw_json.h>
#include <cstdint>
#include <cstddef>

namespace aura {

class ConfigStore;

class WifiManager {
 public:
  using StatusCb = void (*)(const char* status_text, bool online);
  void begin(StatusCb statusCb);
  void update();
  bool isConnected() const;
  void startAPMode();
  bool isAPMode() const { return _ap_mode; }
  const char* getIP() const;
  int getRSSI() const;
  void getLast4Mac(char* out) const;

 private:
  StatusCb _statusCb = nullptr;
  bool _ap_mode = false;
  bool _connected = false;
  int _connect_attempts = 0;
  uint32_t _last_check_ms = 0;
  uint32_t _ap_start_ms = 0;
  char _current_ip[16] = {0};
  int _rssi = 0;
  void doStartAP();
  void handleCaptivePortal();
  bool processProvisioningForm(const char* ssid, const char* pass);
};

class GatewayClient {
 public:
  using InteractCb = void (*)(void* ctx, const GatewayResponse* resp, bool ok);
  using TTSCb = void (*)(void* ctx, const uint8_t* wav, size_t len, bool ok);
  using WakeCb = void (*)(void* ctx, bool woke, const char* text);
  using HealthCb = void (*)(void* ctx, bool ok);

  void begin();
  void update();
  bool isOnline() const;
  void healthz(HealthCb cb, void* ctx);
  void interactText(const char* text, InteractCb cb, void* ctx);
  void interactAudio(const int16_t* pcm16, size_t samples, InteractCb cb, void* ctx);
  void tts(const char* text, TTSCb cb, void* ctx);
  void wake(const int16_t* pcm16, size_t samples, WakeCb cb, void* ctx);
  void reportDeviceStats(int battery_pct, bool charging, int rssi);
  void setGatewayUrl(const char* url);
  void setPowerMonitor(void* pm);  // void* to avoid hal.h dependency

 private:
  char _gateway_url[64] = {0};
  bool _online = false;
  bool _busy = false;
  void* _pending_ctx = nullptr;
  InteractCb _pending_interact_cb = nullptr;
  TTSCb _pending_tts_cb = nullptr;
  WakeCb _pending_wake_cb = nullptr;
  HealthCb _pending_health_cb = nullptr;
  uint32_t _last_req_ms = 0;
  
  enum class TaskState { IDLE, CONNECTING, SENDING, WAITING, RECEIVING, DONE };
  TaskState _task_state = TaskState::IDLE;
  uint8_t _req_buf[4096];
  size_t _req_len = 0;
  char _resp_buf[4096];
  size_t _resp_len = 0;
  
  size_t base64Encode(const uint8_t* src, size_t src_len, char* dst, size_t dst_cap);
  bool validateUrl();
  bool buildInteractRequest(const char* endpoint, const char* text, const char* audio_b64);
  bool buildTTSRequest(const char* text);
  bool buildWakeRequest(const char* audio_b64);
  bool buildStatsRequest(int battery_pct, bool charging, int rssi);
  void parseAndCallback(bool success);
  void transition(TaskState next);
  void doConnect();
  void doSend();
  void doWait();
  void doReceive();
  void doCallback();
};

size_t encodeBase64(const uint8_t* src, size_t src_len, char* dst, size_t dst_cap);

}  // namespace aura
