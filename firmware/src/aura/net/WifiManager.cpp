// WifiManager.cpp - Wi-Fi provisioning with AP fallback and captive portal
// Phase 3: Connect to saved credentials, start AP on fail after 3 attempts
// Uses M5Unified/ESP32 WebServer (Arduino core 2.0.17), NO ESPAsyncWebServer

#include <aura/net.h>
#include <aura/hal.h>
#include <aura/log.h>
#include <aura/events.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <esp_wifi.h>
#include <cstring>

namespace aura {

// Constants
static constexpr int kMaxConnectAttempts = 3;
static constexpr uint32_t kConnectTimeoutMs = 15000;
static constexpr uint32_t kCheckIntervalMs = 2000;
static constexpr uint32_t kAPTimeoutMs = 120000;  // 2 min AP mode timeout
static constexpr const char* kCAPTIVE_PORTAL_PATH = "/";
static constexpr const char* kAP_IP = "192.168.4.1";
static constexpr int kAP_CHANNEL = 1;

class WifiManagerImpl {
 public:
  void begin(WifiManager::StatusCb statusCb) {
    _statusCb = statusCb;
    _last_check_ms = millis();
    
    // Load saved credentials from ConfigStore
    ConfigStore store;
    store.load(_settings);
    
    // Start WiFi in STA mode
    WiFi.mode(WIFI_MODE_STA);
    WiFi.persistent(false);  // Don't auto-save to NVS, we use ConfigStore
    
    if (_settings.wifiSsid[0] != '\0') {
      AURA_LOGF("WiFi connecting to SSID: %.32s", _settings.wifiSsid);
      WiFi.begin(_settings.wifiSsid, _settings.wifiPass);
      _connect_start_ms = millis();
    } else {
      // No saved credentials, go straight to AP mode
      AURA_LOGF("WiFi no saved credentials, starting AP mode");
      startAP();
    }
  }
  
  void update() {
    if (_ap_mode) {
      updateAPMode();
      return;
    }
    
    // Check connection status periodically
    uint32_t now_ms = millis();
    if (now_ms - _last_check_ms < kCheckIntervalMs) return;
    _last_check_ms = now_ms;
    
    wl_status_t status = WiFi.status();
    
    if (status == WL_CONNECTED) {
      if (!_connected) {
        // Just connected
        _connected = true;
        _connect_attempts = 0;
        snprintf(_current_ip, sizeof(_current_ip), "%s", WiFi.localIP().toString().c_str());
        _rssi = WiFi.RSSI();
        AURA_LOGF("WiFi connected: IP=%s RSSI=%d", _current_ip, _rssi);
        if (_statusCb) _statusCb("online", true);
        postEvent(EventKind::NET_ONLINE);
        postEvent(EventKind::GATEWAY_REACHABLE);  // Assume gateway reachable when WiFi up
      }
      // Still connected, check for disconnection
    } else {
      if (_connected) {
        // Just disconnected
        _connected = false;
        AURA_LOGF("WiFi disconnected");
        if (_statusCb) _statusCb("offline", false);
        postEvent(EventKind::NET_OFFLINE);
        postEvent(EventKind::GATEWAY_LOST);
      }
      
      // Reconnection logic
      if (now_ms - _connect_start_ms >= kConnectTimeoutMs || 
          _connect_attempts >= kMaxConnectAttempts) {
        // Connection failed, start AP mode
        AURA_LOGF("WiFi connect failed after %d attempts, starting AP", _connect_attempts);
        startAP();
      }
    }
  }
  
  bool isConnected() const { return _connected && WiFi.status() == WL_CONNECTED; }
  
  void startAPMode() {
    if (!_ap_mode) startAP();
  }
  
  const char* getIP() const {
    if (_connected) {
      return _current_ip;
    } else if (_ap_mode) {
      return kAP_IP;
    }
    return "0.0.0.0";
  }
  
  int getRSSI() const {
    if (_connected) return _rssi;
    return 0;
  }
  
  void getLast4Mac(char* out) const {
    uint8_t mac[6];
    if (WiFi.macAddress(mac)) {
      snprintf(out, 5, "%02X%02X", mac[4], mac[5]);
    } else {
      snprintf(out, 5, "0000");
    }
  }
  
 private:
  WifiManager::StatusCb _statusCb = nullptr;
  DeviceSettings _settings;
  bool _ap_mode = false;
  bool _connected = false;
  int _connect_attempts = 0;
  uint32_t _connect_start_ms = 0;
  uint32_t _last_check_ms = 0;
  char _current_ip[16] = {0};
  int _rssi = 0;
  
  // AP mode components
  WebServer* _server = nullptr;
  DNSServer* _dns = nullptr;
  uint32_t _ap_start_ms = 0;
  
  void startAP() {
    _ap_mode = true;
    _ap_start_ms = millis();
    
    // Get last 4 chars of MAC for AP name
    char last4mac[5];
    getLast4Mac(last4mac);
    char apName[32];
    snprintf(apName, sizeof(apName), "AURA-%s", last4mac);
    
    // Stop STA
    WiFi.mode(WIFI_MODE_NULL);
    delay(100);
    
    // Start AP
    WiFi.mode(WIFI_MODE_AP);
    WiFi.softAP(apName, nullptr);  // Open AP, no password
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), 
                      IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    
    AURA_LOGF("WiFi AP started: %s", apName);
    if (_statusCb) _statusCb("ap_mode", false);
    
    // Setup DNS server for captive portal
    _dns = new DNSServer();
    _dns->start(53, "*", IPAddress(192, 168, 4, 1));
    
    // Setup Web server
    _server = new WebServer(80);
    
    // Captive portal routes
    _server->on("/", [this]() { handleRoot(); });
    _server->on("/provision", [this]() { handleProvision(); });
    _server->onNotFound([this]() { handleRoot(); });
    
    _server->begin();
    AURA_LOGF("WiFi Web server started on port 80");
  }
  
  void updateAPMode() {
    // Check if AP should timeout
    if (millis() - _ap_start_ms >= kAPTimeoutMs) {
      AURA_LOGF("WiFi AP timeout, restarting");
      stopAP();
      _ap_mode = false;
      _connect_attempts = 0;
      begin(_statusCb);  // Restart connection attempt
      return;
    }
    
    // Process web server
    if (_server) {
      _server->handleClient();
    }
    
    // Process DNS
    if (_dns) {
      _dns->processNextRequest();
    }
  }
  
  void stopAP() {
    if (_server) {
      _server->stop();
      delete _server;
      _server = nullptr;
    }
    if (_dns) {
      _dns->stop();
      delete _dns;
      _dns = nullptr;
    }
    WiFi.mode(WIFI_MODE_NULL);
  }
  
  void handleRoot() {
    // Captive portal HTML - HTML-escaped form
    const char* html = 
      "<!DOCTYPE html><html><head>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>AURA Provisioning</title>"
      "<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:linear-gradient(135deg,#040a18,#0a1628);color:#fff}</style>"
      "</head><body><div style='max-width:320px;padding:24px;background:rgba(255,255,255,0.1);border-radius:16px;backdrop-filter:blur(10px)'>"
      "<h1 style='margin:0 0 24px'>AURA Setup</h1>"
      "<form method='POST' action='/provision'>"
      "<div style='margin-bottom:16px'><label for='ssid' style='display:block;margin-bottom:8px'>Network (SSID)</label>"
      "<input type='text' id='ssid' name='ssid' required style='width:100%;padding:10px;border:none;border-radius:8px;font-size:16px'></div>"
      "<div style='margin-bottom:24px'><label for='pass' style='display:block;margin-bottom:8px'>Password</label>"
      "<input type='password' id='pass' name='pass' style='width:100%;padding:10px;border:none;border-radius:8px;font-size:16px'></div>"
      "<button type='submit' style='width:100%;padding:12px;background:#8cf5d2;border:none;border-radius:8px;font-size:16px;color:#040a18;font-weight:600;cursor:pointer'>Save & Reboot</button>"
      "</form>"
      "</div></body></html>";
    
    _server->send(200, "text/html; charset=utf-8", html);
  }
  
  void handleProvision() {
    if (_server->hasArg("ssid") && _server->hasArg("pass")) {
      // Store raw values; the portal never echoes inputs back into HTML,
      // so escaping is unnecessary here and would corrupt passwords.
      String ssid = _server->arg("ssid");
      String pass = _server->arg("pass");
      
      AURA_LOGF("WiFi provisioning SSID=%.32s pass_len=%d", ssid.c_str(), pass.length());
      
      // Save credentials to ConfigStore
      if (processProvisioningForm(ssid.c_str(), pass.c_str())) {
        _server->send(200, "text/html", 
          "<!DOCTYPE html><html><body style='font-family:system-ui;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:linear-gradient(135deg,#040a18,#0a1628);color:#fff'><div style='text-align:center'><h1> saved!</h1><p>Rebooting...</p></div></body></html>");
        
        // Reboot after short delay
        delay(1000);
        ESP.restart();
      } else {
        _server->send(500, "text/plain", "Failed to save credentials");
      }
    } else {
      handleRoot();
    }
  }
  
  bool processProvisioningForm(const char* ssid, const char* pass) {
    if (strlen(ssid) == 0 || strlen(ssid) > 32) {
      AURA_LOGW("WiFi invalid SSID length");
      return false;
    }
    
    // Copy to settings
    strncpy(_settings.wifiSsid, ssid, 32);
    _settings.wifiSsid[32] = '\0';
    strncpy(_settings.wifiPass, pass, 64);
    _settings.wifiPass[64] = '\0';
    
    // Save to ConfigStore
    ConfigStore store;
    if (!store.save(_settings)) {
      AURA_LOGW("WiFi failed to save credentials");
      return false;
    }
    
    AURA_LOGF("WiFi credentials saved, rebooting");
    return true;
  }
  
  // HTML escape helper - escapes < > & " ' to prevent injection
  String escapeHtml(const String& input) {
    String result = input;
    result.replace("&", "&amp;");
    result.replace("<", "&lt;");
    result.replace(">", "&gt;");
    result.replace("\"", "&quot;");
    result.replace("'", "&#39;");
    return result;
  }
  
  void postEvent(EventKind kind) {
    Event e{kind, 0, 0, 0};
    EventBus::instance().post(e);
  }
};

static WifiManagerImpl g_wifiImpl;

void WifiManager::begin(StatusCb statusCb) {
  g_wifiImpl.begin(statusCb);
}

void WifiManager::update() {
  g_wifiImpl.update();
}

bool WifiManager::isConnected() const {
  return g_wifiImpl.isConnected();
}

void WifiManager::startAPMode() {
  g_wifiImpl.startAPMode();
}

const char* WifiManager::getIP() const {
  return g_wifiImpl.getIP();
}

int WifiManager::getRSSI() const {
  return g_wifiImpl.getRSSI();
}

void WifiManager::getLast4Mac(char* out) const {
  g_wifiImpl.getLast4Mac(out);
}

}  // namespace aura
