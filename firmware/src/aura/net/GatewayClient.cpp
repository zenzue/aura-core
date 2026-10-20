// GatewayClient.cpp - HTTP client for gateway API with async pattern
// Phase 3: Non-blocking HTTP client using WiFiClient + HTTPClient (Arduino core 2.0.17)

#include <aura/net.h>
#include <aura/hal.h>
#include <aura/log.h>
#include <aura/audio.h>
#include <aura/gw_json.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <cstring>

namespace aura {

static constexpr uint32_t kHTTPTimeoutMs = 15000;
static constexpr uint32_t kRetryIntervalMs = 5000;

struct SizeTracker {
  size_t cap = 0;
  void add(size_t n) { cap += n; }
};

static PowerMonitor* s_powerMonitor = nullptr;

static const size_t kWavHeaderSize = 44;

static size_t appendJsonEscaped(char* out, size_t cap, size_t pos, const char* text) {
  if (pos + 1 >= cap) return pos;
  out[pos++] = '"';
  for (const char* p = text; *p && pos + 7 < cap; p++) {
    switch (*p) {
      case '"':  out[pos++] = '\\'; out[pos++] = '"'; break;
      case '\\': out[pos++] = '\\'; out[pos++] = '\\'; break;
      case '\n': out[pos++] = '\\'; out[pos++] = 'n'; break;
      case '\r': out[pos++] = '\\'; out[pos++] = 'r'; break;
      case '\t': out[pos++] = '\\'; out[pos++] = 't'; break;
      default: out[pos++] = *p; break;
    }
  }
  if (pos + 1 < cap) out[pos++] = '"';
  return pos;
}

static void buildWavHeader(uint8_t* buf, uint32_t num_samples, uint32_t sample_rate) {
  const uint32_t pcmBytes = num_samples * sizeof(int16_t);
  uint8_t* p = buf;
  uint32_t v32;

  memcpy(p, "RIFF", 4); p += 4;
  v32 = kWavHeaderSize + pcmBytes - 8; memcpy(p, &v32, 4); p += 4;
  memcpy(p, "WAVEfmt ", 8); p += 8;
  v32 = 16; memcpy(p, &v32, 4); p += 4;
  uint16_t v16;
  v16 = 1; memcpy(p, &v16, 2); p += 2;
  v16 = 1; memcpy(p, &v16, 2); p += 2;
  v32 = sample_rate; memcpy(p, &v32, 4); p += 4;
  v32 = sample_rate * 2; memcpy(p, &v32, 4); p += 4;
  v16 = 2; memcpy(p, &v16, 2); p += 2;
  v16 = 16; memcpy(p, &v16, 2); p += 2;
  memcpy(p, "data", 4); p += 4;
  v32 = pcmBytes; memcpy(p, &v32, 4); p += 4;
}


class GatewayClientImpl {
 public:
  void begin() {
    ConfigStore store;
    DeviceSettings settings;
    if (store.load(settings)) {
      setGatewayUrl(settings.gatewayUrl);
    }
  }
  
  void update() {
    if (_task_state == TaskState::IDLE) return;
    
    switch (_task_state) {
      case TaskState::CONNECTING:
        doConnect();
        break;
      case TaskState::SENDING:
        doSend();
        break;
      case TaskState::WAITING:
        doWait();
        break;
      case TaskState::RECEIVING:
        doReceive();
        break;
      case TaskState::DONE:
        doCallback();
        break;
      default:
        transition(TaskState::IDLE);
        break;
    }
  }
  
  void setGatewayUrl(const char* url) {
    strncpy(_gateway_url, url, sizeof(_gateway_url) - 1);
    _gateway_url[sizeof(_gateway_url) - 1] = '\0';
    AURA_LOGF("Gateway URL set: %.63s", _gateway_url);
  }
  
  bool isOnline() const { return _online; }
  bool isBusy() const { return _busy; }
  bool hasUrl() const { return _gateway_url[0] != '\0'; }
  
  void healthz(GatewayClient::HealthCb cb, void* ctx) {
    if (_busy || !validateUrl()) {
      if (cb) cb(ctx, false);
      return;
    }
    
    _pending_health_cb = cb;
    _pending_ctx = ctx;
    _req_endpoint = "/healthz";
    _req_method = "GET";
    _req_body = nullptr;
    _req_body_len = 0;
    
    transition(TaskState::CONNECTING);
  }
  
  void interactText(const char* text, GatewayClient::InteractCb cb, void* ctx) {
    if (_busy || !validateUrl()) {
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    if (!buildInteractRequest("/interact", text, nullptr, 0, 0)) {
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    _pending_interact_cb = cb;
    _pending_ctx = ctx;
    transition(TaskState::CONNECTING);
  }
  
  void interactAudio(const int16_t* pcm16, size_t samples, 
                     GatewayClient::InteractCb cb, void* ctx) {
    if (_busy || !validateUrl()) {
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    if (!pcm16 || samples == 0) {
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    const size_t pcmBytes = samples * sizeof(int16_t);
    const size_t wavLen = kWavHeaderSize + pcmBytes;
    const size_t base64Cap = wavLen * 4 / 3 + 8;
    
    char* audio_b64 = static_cast<char*>(heap_caps_malloc(base64Cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!audio_b64) {
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    uint8_t* wav_buf = static_cast<uint8_t*>(heap_caps_malloc(wavLen, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!wav_buf) {
      heap_caps_free(audio_b64);
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    buildWavHeader(wav_buf, static_cast<uint32_t>(samples), 16000);
    memcpy(wav_buf + kWavHeaderSize, pcm16, pcmBytes);
    
    size_t b64Len = encodeBase64(wav_buf, wavLen, audio_b64, base64Cap);
    
    heap_caps_free(wav_buf);
    
    if (b64Len == 0) {
      heap_caps_free(audio_b64);
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    if (!buildInteractRequest("/interact", nullptr, audio_b64, b64Len, 0)) {
      heap_caps_free(audio_b64);
      if (cb) cb(ctx, nullptr, false);
      return;
    }
    
    heap_caps_free(audio_b64);
    
    _pending_interact_cb = cb;
    _pending_ctx = ctx;
    transition(TaskState::CONNECTING);
  }
  
  void tts(const char* text, GatewayClient::TTSCb cb, void* ctx) {
    if (_busy || !validateUrl()) {
      if (cb) cb(ctx, nullptr, 0, false);
      return;
    }
    
    if (!buildTTSRequest(text)) {
      if (cb) cb(ctx, nullptr, 0, false);
      return;
    }
    
    _pending_tts_cb = cb;
    _pending_ctx = ctx;
    transition(TaskState::CONNECTING);
  }
  
  void wake(const int16_t* pcm16, size_t samples,
            GatewayClient::WakeCb cb, void* ctx) {
    if (_busy || !validateUrl()) {
      if (cb) cb(ctx, false, nullptr);
      return;
    }
    
    if (!pcm16 || samples == 0) {
      if (cb) cb(ctx, false, nullptr);
      return;
    }
    
    if (!buildWakeRequest(pcm16, samples)) {
      if (cb) cb(ctx, false, nullptr);
      return;
    }
    
    _pending_wake_cb = cb;
    _pending_ctx = ctx;
    transition(TaskState::CONNECTING);
  }
  
  void reportDeviceStats(int battery_pct, bool charging, int rssi) {
    if (!validateUrl()) return;
    
    if (buildStatsRequest(battery_pct, charging, rssi)) {
      _pending_ctx = nullptr;
      _pending_health_cb = nullptr;
      transition(TaskState::CONNECTING);
    }
  }
  
  void setPowerMonitor(PowerMonitor* pm) {
    s_powerMonitor = pm;
  }
  
 private:
  enum class TaskState { IDLE, CONNECTING, SENDING, WAITING, RECEIVING, DONE };
  
  char _gateway_url[64] = {0};
  bool _online = false;
  bool _busy = false;
  TaskState _task_state = TaskState::IDLE;
  
  void* _pending_ctx = nullptr;
  GatewayClient::InteractCb _pending_interact_cb = nullptr;
  GatewayClient::TTSCb _pending_tts_cb = nullptr;
  GatewayClient::WakeCb _pending_wake_cb = nullptr;
  GatewayClient::HealthCb _pending_health_cb = nullptr;
  
  String _req_endpoint;
  String _req_method;
  const char* _req_body = nullptr;
  size_t _req_body_len = 0;
  
  char* _resp_buf = nullptr;
  size_t _resp_len = 0;
  size_t _resp_cap = 0;
  size_t _content_len = 0;
  bool _headers_done = false;
  bool _status_seen = false;
  char _wake_text[128] = {0};
  static const size_t kMaxRespBytes = 512 * 1024;
  
  WiFiClient _client;
  int _http_code = 0;
  void* _dynamic_body = nullptr;
  
  bool validateUrl() {
    if (_gateway_url[0] == '\0') {
      AURA_LOGW("Gateway URL not set");
      return false;
    }
    return true;
  }
  
  bool buildInteractRequest(const char* endpoint, const char* text, const char* audio_b64,
                            size_t audio_b64_len, int rssi) {
    SizeTracker sz;
    
    sz.add(1024);
    if (text) sz.add(strlen(text) * 6);
    if (audio_b64) sz.add(2 + audio_b64_len + 20);
    sz.add(200);
    
    uint8_t* body = static_cast<uint8_t*>(heap_caps_malloc(sz.cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!body) return false;
    
    size_t pos = 0;
    char* out = reinterpret_cast<char*>(body);
    
    pos += snprintf(out + pos, sz.cap - pos, "{\"device_id\":\"core2\"");
    
    if (text) {
      pos += snprintf(out + pos, sz.cap - pos, ",\"text\":");
      pos = appendJsonEscaped(out, sz.cap, pos, text);
    }
    
    if (audio_b64 && audio_b64_len > 0) {
      pos += snprintf(out + pos, sz.cap - pos, ",\"audio_wav_b64\":\"%.*s\"", static_cast<int>(audio_b64_len), audio_b64);
    }
    
    pos += snprintf(out + pos, sz.cap - pos, ",\"locale\":\"en-US\"");
    
    int bat = s_powerMonitor ? s_powerMonitor->batteryPercent() : 0;
    bool chg = s_powerMonitor ? s_powerMonitor->isCharging() : false;
    pos += snprintf(out + pos, sz.cap - pos, ",\"device_battery\":%d", bat);
    pos += snprintf(out + pos, sz.cap - pos, ",\"device_charging\":%s", chg ? "true" : "false");
    
    if (rssi != 0) {
      pos += snprintf(out + pos, sz.cap - pos, ",\"rssi\":%d", rssi);
    }
    
    pos += snprintf(out + pos, sz.cap - pos, ",\"tts\":true}");
    
    _req_endpoint = endpoint;
    _req_method = "POST";
    _req_body = reinterpret_cast<const char*>(body);
    _req_body_len = pos;
    _dynamic_body = body;
    
    AURA_LOGF("Built interact request len=%zu", pos);
    return true;
  }
  
  bool buildTTSRequest(const char* text) {
    size_t bodyCap = 512;
    uint8_t* body = static_cast<uint8_t*>(
        heap_caps_malloc(bodyCap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!body) return false;
    
    char* out = reinterpret_cast<char*>(body);
    size_t pos = snprintf(out, bodyCap, "{\"text\":");
    pos = appendJsonEscaped(out, bodyCap, pos, text ? text : "");
    if (pos + 2 < bodyCap) { out[pos++] = '}'; out[pos] = '\0'; }
    int len = static_cast<int>(pos);
    
    _req_endpoint = "/tts";
    _req_method = "POST";
    _req_body = reinterpret_cast<const char*>(body);
    _req_body_len = len < 0 ? 0 : len;
    _dynamic_body = body;
    
    return _req_body_len > 0;
  }
  
  bool buildWakeRequest(const int16_t* pcm16, size_t samples) {
    const size_t wavLen = kWavHeaderSize + samples * sizeof(int16_t);
    const size_t b64Cap = wavLen * 4 / 3 + 8;
    const size_t bodyCap = b64Cap + 128;
    uint8_t* body = static_cast<uint8_t*>(
        heap_caps_malloc(bodyCap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!body) return false;
    char* out = reinterpret_cast<char*>(body);
    
    size_t pos = 0;
    uint8_t* wav_buf = static_cast<uint8_t*>(
        heap_caps_malloc(wavLen, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!wav_buf) { heap_caps_free(body); return false; }
    buildWavHeader(wav_buf, static_cast<uint32_t>(samples), 16000);
    memcpy(wav_buf + kWavHeaderSize, pcm16, samples * sizeof(int16_t));
    
    pos += snprintf(out + pos, bodyCap - pos, "{\"audio_b64\":\"");
    size_t b64Len = encodeBase64(wav_buf, wavLen, out + pos, bodyCap - pos - 32);
    heap_caps_free(wav_buf);
    if (b64Len == 0) { heap_caps_free(body); return false; }
    pos += b64Len;
    pos += snprintf(out + pos, bodyCap - pos, "\",\"client_id\":\"core2\"}");
    
    _req_endpoint = "/wake";
    _req_method = "POST";
    _req_body = out;
    _req_body_len = pos;
    _dynamic_body = body;
    return true;
  }
  
  bool buildStatsRequest(int battery_pct, bool charging, int rssi) {
    size_t bodyCap = 512;
    uint8_t* body = static_cast<uint8_t*>(
        heap_caps_malloc(bodyCap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!body) return false;
    
    String ipStr = WiFi.localIP().toString();
    String ssidStr = WiFi.SSID();
    const char* ip = ipStr.c_str();
    const char* ssid = ssidStr.c_str();
    
    int len = snprintf(reinterpret_cast<char*>(body), bodyCap,
                       "{\"device_id\":\"core2\",\"online\":true,\"battery\":%d,"
                       "\"charging\":%s,\"rssi\":%d,\"ip\":\"%s\",\"ssid\":\"%s\",\"fw_version\":\"1.0.0\"}",
                       battery_pct, charging ? "true" : "false", rssi, ip, ssid);
    
    _req_endpoint = "/stats";
    _req_method = "POST";
    _req_body = reinterpret_cast<const char*>(body);
    _req_body_len = len < 0 ? 0 : len;
    _dynamic_body = body;
    
    return _req_body_len > 0;
  }
  
  void doConnect() {
    if (!_client.connect(_gateway_url, 80, kHTTPTimeoutMs)) {
      AURA_LOGW("Gateway connect failed");
      _online = false;
      doCallback();
      return;
    }
    
    _online = true;
    transition(TaskState::SENDING);
  }
  
  void doSend() {
    String request = _req_method + " " + _req_endpoint + " HTTP/1.1\r\n"
                     "Host: " + _gateway_url + "\r\n"
                     "Content-Type: application/json\r\n"
                     "Connection: close\r\n";
    
    if (_req_body_len > 0) {
      request += "Content-Length: " + String(_req_body_len) + "\r\n";
    }
    
    request += "\r\n";
    
    if (!_client.print(request)) {
      AURA_LOGW("Failed to send request header");
      doCallback();
      return;
    }
    
    if (_req_body && _req_body_len > 0) {
      if (_client.write(reinterpret_cast<const uint8_t*>(_req_body), _req_body_len) != _req_body_len) {
        AURA_LOGW("Failed to send request body");
      }
    }
    
    transition(TaskState::WAITING);
  }
  
  void doWait() {
    if (!_client.connected() && !_client.available()) {
      transition(TaskState::DONE);
      return;
    }
    
    if (_client.available()) {
      transition(TaskState::RECEIVING);
    }
  }
  
  void doReceive() {
    if (!_headers_done) {
      while (_client.available()) {
        String line = _client.readStringUntil('\n');
        int nl = line.length() - 1;
        while (nl >= 0 && (line.charAt(nl) == '\r' || line.charAt(nl) == '\n')) nl--;
        line.remove(nl + 1);
        if (line.length() == 0) {
          if (_status_seen) { _headers_done = true; break; }
          continue;
        }
        if (!_status_seen) {
          _status_seen = true;
          _http_code = line.substring(9, 12).toInt();
          continue;
        }
        if (line.startsWith("Content-Length:")) {
          _content_len = line.substring(15).toInt();
        }
      }
      if (!_headers_done) return;
      if (_http_code == 0) {
        AURA_LOGW("Gateway: unparsable HTTP status");
        _client.stop();
        transition(TaskState::DONE);
        return;
      }
      size_t cap = (_content_len > 0 && _content_len <= kMaxRespBytes)
                       ? _content_len : kMaxRespBytes;
      _resp_buf = static_cast<char*>(
          heap_caps_malloc(cap + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
      if (!_resp_buf) {
        AURA_LOGW("Gateway: response alloc failed cap=%zu", cap);
        _client.stop();
        transition(TaskState::DONE);
        return;
      }
      _resp_cap = cap;
    }

    int budget = 16384;
    while (_client.available() > 0 && _resp_len < _resp_cap && budget > 0) {
      int want = _client.available();
      if (want > static_cast<int>(_resp_cap - _resp_len)) want = _resp_cap - _resp_len;
      if (want > budget) want = budget;
      int got = _client.readBytes(_resp_buf + _resp_len, want);
      if (got <= 0) break;
      _resp_len += got;
      budget -= got;
    }

    bool complete = (_content_len > 0)
                        ? (_resp_len >= _content_len)
                        : (!_client.available() && !_client.connected());
    if (complete || _resp_len >= _resp_cap) {
      if (_content_len > 0 && _resp_len < _content_len) {
        AURA_LOGW("Gateway: response truncated %zu/%zu", _resp_len, _content_len);
        _http_code = 0;
      }
      _client.stop();
      transition(TaskState::DONE);
    }
  }

  void doCallback() {
    _busy = false;
    
    if (_req_body && _dynamic_body) {
      heap_caps_free(const_cast<char*>(_req_body));
      _req_body = nullptr;
      _dynamic_body = nullptr;
    }
    
    bool success = _online && _http_code >= 200 && _http_code < 300;
    
    if (_pending_health_cb) {
      _pending_health_cb(_pending_ctx, success);
      _pending_health_cb = nullptr;
    } else if (_pending_interact_cb) {
      GatewayResponse resp;
      if (success) {
        parseGatewayResponse(_resp_buf, _resp_len, resp);
      }
      _pending_interact_cb(_pending_ctx, &resp, success);
      freeGatewayResponseAudio(resp);
      _pending_interact_cb = nullptr;
    } else if (_pending_tts_cb) {
      if (success) {
        _pending_tts_cb(_pending_ctx, 
                        reinterpret_cast<const uint8_t*>(_resp_buf), 
                        _resp_len, true);
      } else {
        _pending_tts_cb(_pending_ctx, nullptr, 0, false);
      }
      _pending_tts_cb = nullptr;
    } else if (_pending_wake_cb) {
      bool woke = false;
      const char* text = nullptr;
      
      if (success) {
        StringSpan wokeSpan = extractJsonStringSpan(_resp_buf, _resp_len, "woke");
        if (wokeSpan.ptr && wokeSpan.len > 0) {
          woke = (wokeSpan.len == 4 && strncmp(wokeSpan.ptr, "true", 4) == 0);
        }
        StringSpan textSpan = extractJsonStringSpan(_resp_buf, _resp_len, "text");
        if (textSpan.ptr && textSpan.len > 0) {
          size_t n = textSpan.len < sizeof(_wake_text) - 1 ? textSpan.len : sizeof(_wake_text) - 1;
          memcpy(_wake_text, textSpan.ptr, n);
          _wake_text[n] = '\0';
          text = _wake_text;
        }
      }
      
      _pending_wake_cb(_pending_ctx, woke, text);
      _pending_wake_cb = nullptr;
    }
    
    if (_resp_buf) {
      heap_caps_free(_resp_buf);
      _resp_buf = nullptr;
    }
    _resp_cap = 0;
    _resp_len = 0;
    _content_len = 0;
    _headers_done = false;
    _status_seen = false;
    _wake_text[0] = '\0';
    _http_code = 0;
    transition(TaskState::IDLE);
  }
  
  void transition(TaskState next) {
    AURA_LOGF("Gateway task %d->%d", static_cast<int>(_task_state), static_cast<int>(next));
    _task_state = next;
  }
};

static GatewayClientImpl g_gatewayImpl;

void GatewayClient::begin() {
  g_gatewayImpl.begin();
}

void GatewayClient::update() {
  g_gatewayImpl.update();
}

bool GatewayClient::isOnline() const {
  return g_gatewayImpl.isOnline();
}

bool GatewayClient::isBusy() const {
  return g_gatewayImpl.isBusy();
}

bool GatewayClient::hasUrl() const {
  return g_gatewayImpl.hasUrl();
}

void GatewayClient::healthz(HealthCb cb, void* ctx) {
  g_gatewayImpl.healthz(cb, ctx);
}

void GatewayClient::interactText(const char* text, InteractCb cb, void* ctx) {
  g_gatewayImpl.interactText(text, cb, ctx);
}

void GatewayClient::interactAudio(const int16_t* pcm16, size_t samples,
                                  InteractCb cb, void* ctx) {
  g_gatewayImpl.interactAudio(pcm16, samples, cb, ctx);
}

void GatewayClient::tts(const char* text, TTSCb cb, void* ctx) {
  g_gatewayImpl.tts(text, cb, ctx);
}

void GatewayClient::wake(const int16_t* pcm16, size_t samples,
                         WakeCb cb, void* ctx) {
  g_gatewayImpl.wake(pcm16, samples, cb, ctx);
}

void GatewayClient::reportDeviceStats(int battery_pct, bool charging, int rssi) {
  g_gatewayImpl.reportDeviceStats(battery_pct, charging, rssi);
}

void GatewayClient::setGatewayUrl(const char* url) {
  g_gatewayImpl.setGatewayUrl(url);
}

void GatewayClient::setPowerMonitor(void* pm) {
  g_gatewayImpl.setPowerMonitor(static_cast<PowerMonitor*>(pm));
}

}  // namespace aura
