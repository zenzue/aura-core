// gw_json.h - Gateway JSON helpers (base64, parsing, response management)
#pragma once

#include <cstdint>
#include <cstddef>

namespace aura {

size_t encodeBase64(const uint8_t* src, size_t src_len, char* dst, size_t dst_cap);
size_t decodeBase64(const char* src, size_t src_len, uint8_t* dst, size_t dst_cap);

struct StringSpan {
  const char* ptr;
  size_t len;
};

StringSpan extractJsonStringSpan(const char* json, size_t len, const char* key);

struct GatewayResponse {
  char spoken_text[512];
  char emotion[32];
  float expression_intensity;
  char animation_hint[64];
  char action_type[32];
  char action_text[256];
  int action_level;
  int action_ms;
  uint8_t* wav;
  size_t wav_len;
  bool has_audio;
  bool parse_ok;
};

bool parseGatewayResponse(const char* json, size_t len, GatewayResponse& out);
void freeGatewayResponseAudio(GatewayResponse& resp);
void freeGatewayResponseAudio(const GatewayResponse& resp);

}  // namespace aura
