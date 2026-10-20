// gw_json.cpp - Gateway JSON helpers (base64, parsing, response management)

#include <aura/gw_json.h>
#include <aura/log.h>
#include <cstring>
#include <cctype>

namespace aura {

static const char kBase64Chars[] = 
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

size_t encodeBase64(const uint8_t* src, size_t src_len, char* dst, size_t dst_cap) {
  if (!src || !dst || src_len == 0) return 0;
  
  size_t dst_idx = 0;
  size_t src_idx = 0;
  
  while (src_idx < src_len) {
    if (dst_idx + 4 >= dst_cap) break;
    
    uint32_t b = 0;
    uint8_t remaining = 0;
    
    for (int i = 0; i < 3 && src_idx < src_len; i++, src_idx++) {
      b = (b << 8) | src[src_idx];
      remaining++;
    }
    
    b <<= (3 - remaining) * 8;
    
    dst[dst_idx++] = kBase64Chars[(b >> 18) & 0x3F];
    dst[dst_idx++] = kBase64Chars[(b >> 12) & 0x3F];
    
    if (remaining >= 2) {
      dst[dst_idx++] = kBase64Chars[(b >> 6) & 0x3F];
    } else {
      dst[dst_idx++] = '=';
    }
    
    if (remaining >= 3) {
      dst[dst_idx++] = kBase64Chars[b & 0x3F];
    } else {
      dst[dst_idx++] = '=';
    }
  }
  
  dst[dst_idx] = '\0';
  return dst_idx;
}

size_t decodeBase64(const char* src, size_t src_len, uint8_t* dst, size_t dst_cap) {
  if (!src || !dst || src_len == 0) return 0;
  
  static const int8_t kDecodeTable[256] = {
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
    52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-1,-1,-1,
    -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
    15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
    -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
    41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
  };
  
  size_t out_idx = 0;
  size_t i = 0;
  
  while (i < src_len) {
    while (i < src_len && (src[i] == ' ' || src[i] == '\t' || 
           src[i] == '\r' || src[i] == '\n')) i++;
    if (i >= src_len) break;
    
    int8_t c0 = kDecodeTable[(unsigned char)src[i]];
    if (c0 < 0) return 0;
    i++;
    
    if (i >= src_len) return 0;
    int8_t c1 = kDecodeTable[(unsigned char)src[i]];
    if (c1 < 0) return 0;
    i++;
    
    uint32_t b = (c0 << 6) | c1;
    
    if (i >= src_len) return 0;
    char c2_char = src[i];
    if (c2_char == '=') {
      if (out_idx < dst_cap) dst[out_idx++] = (b >> 4) & 0xFF;
      break;
    }
    int8_t c2 = kDecodeTable[(unsigned char)c2_char];
    if (c2 < 0) return 0;
    i++;
    
    b = (b << 6) | c2;
    
    if (out_idx + 1 < dst_cap) {
      dst[out_idx++] = (b >> 10) & 0xFF;
      dst[out_idx++] = (b >> 2) & 0xFF;
    } else if (out_idx < dst_cap) {
      dst[out_idx++] = (b >> 10) & 0xFF;
    } else {
      break;
    }
    
    if (i >= src_len) break;
    char c3_char = src[i];
    if (c3_char == '=') {
      break;
    }
    int8_t c3 = kDecodeTable[(unsigned char)c3_char];
    if (c3 < 0) return 0;
    i++;
    
    b = (b << 6) | c3;
    
    if (out_idx < dst_cap) {
      dst[out_idx++] = b & 0xFF;
    }
  }
  
  return out_idx;
}

StringSpan extractJsonStringSpan(const char* json, size_t len, const char* key) {
  StringSpan span = {nullptr, 0};
  
  if (!json || !key || len == 0) return span;
  
  char searchKey[64];
  int keyLen = snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
  if (keyLen <= 0 || keyLen >= (int)sizeof(searchKey)) return span;
  
  const char* keyPos = static_cast<const char*>(memmem(json, len, searchKey, keyLen));
  if (!keyPos) return span;
  
  const char* colon = strchr(keyPos + keyLen, ':');
  if (!colon) return span;
  colon++;
  while (colon < json + len && (*colon == ' ' || *colon == '\t')) colon++;
  
  if (colon >= json + len || *colon != '"') return span;
  
  const char* start = colon + 1;
  const char* end = start;
  while (end < json + len && *end != '"') {
    if (*end == '\\' && end + 1 < json + len) end++;
    end++;
  }
  
  if (*end != '"') return span;
  
  span.ptr = start;
  span.len = end - start;
  
  return span;
}

static bool findJsonString(const char* json, size_t len, const char* key, 
                           char* out, size_t outCap, size_t* outLen) {
  StringSpan span = extractJsonStringSpan(json, len, key);
  if (!span.ptr) {
    if (outLen) *outLen = 0;
    out[0] = '\0';
    return true;
  }
  
  size_t copyLen = span.len < outCap - 1 ? span.len : outCap - 1;
  memcpy(out, span.ptr, copyLen);
  out[copyLen] = '\0';
  if (outLen) *outLen = copyLen;
  
  return true;
}

static bool findJsonFloat(const char* json, size_t len, const char* key, float* out) {
  StringSpan span = extractJsonStringSpan(json, len, key);
  if (span.ptr) {
    char buf[32];
    size_t copyLen = span.len < sizeof(buf) - 1 ? span.len : sizeof(buf) - 1;
    memcpy(buf, span.ptr, copyLen);
    buf[copyLen] = '\0';
    char* end;
    *out = strtof(buf, &end);
    return end > buf;
  }
  
  char searchKey[64];
  int keyLen = snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
  if (keyLen <= 0) return false;
  
  const char* keyPos = static_cast<const char*>(memmem(json, len, searchKey, keyLen));
  if (!keyPos) return false;
  
  const char* colon = strchr(keyPos + keyLen, ':');
  if (!colon) return false;
  colon++;
  while (colon < json + len && (*colon == ' ' || *colon == '\t')) colon++;
  
  if (colon >= json + len) return false;
  
  char* end;
  *out = strtof(colon, &end);
  return end > colon;
}

static bool findJsonObject(const char* json, size_t len, const char* key,
                           const char** out_start, size_t* out_len) {
  char searchKey[64];
  int keyLen = snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
  if (keyLen <= 0) return false;
  
  const char* keyPos = static_cast<const char*>(memmem(json, len, searchKey, keyLen));
  if (!keyPos) return false;
  
  const char* colon = strchr(keyPos + keyLen, ':');
  if (!colon) return false;
  colon++;
  while (colon < json + len && (*colon == ' ' || *colon == '\t')) colon++;
  
  if (colon >= json + len || *colon != '{') return false;
  
  int depth = 1;
  const char* start = colon;
  colon++;
  while (colon < json + len && depth > 0) {
    if (*colon == '{') depth++;
    else if (*colon == '}') depth--;
    colon++;
  }
  
  if (depth != 0) return false;
  
  *out_start = start;
  *out_len = colon - start;
  return true;
}

static bool parseActionFields(const char* actionJson, size_t actionLen, 
                              char* type_out, size_t type_cap,
                              char* text_out, size_t text_cap,
                              int* level_out, int* ms_out) {
  findJsonString(actionJson, actionLen, "type", type_out, type_cap, nullptr);
  findJsonString(actionJson, actionLen, "text", text_out, text_cap, nullptr);
  
  char searchKey[32];
  const char* pos;
  
  snprintf(searchKey, sizeof(searchKey), "\"level\"");
  pos = static_cast<const char*>(memmem(actionJson, actionLen, searchKey, strlen(searchKey)));
  if (pos) {
    const char* colon = strchr(pos + 8, ':');
    if (colon) {
      colon++;
      while (colon < actionJson + actionLen && (*colon == ' ' || *colon == '\t')) colon++;
      if (colon < actionJson + actionLen) {
        char* end;
        *level_out = static_cast<int>(strtol(colon, &end, 10));
      }
    }
  }
  
  snprintf(searchKey, sizeof(searchKey), "\"ms\"");
  pos = static_cast<const char*>(memmem(actionJson, actionLen, searchKey, strlen(searchKey)));
  if (pos) {
    const char* colon = strchr(pos + 5, ':');
    if (colon) {
      colon++;
      while (colon < actionJson + actionLen && (*colon == ' ' || *colon == '\t')) colon++;
      if (colon < actionJson + actionLen) {
        char* end;
        *ms_out = static_cast<int>(strtol(colon, &end, 10));
      }
    }
  }
  
  return true;
}

bool parseGatewayResponse(const char* json, size_t len, GatewayResponse& out) {
  out = GatewayResponse{};
  out.expression_intensity = 1.0f;
  out.action_level = 0;
  out.action_ms = 0;
  out.wav = nullptr;
  out.wav_len = 0;
  out.parse_ok = false;
  
  if (!json || len == 0) return false;
  
  if (!findJsonString(json, len, "spoken_text", out.spoken_text, sizeof(out.spoken_text), nullptr)) {
    return false;
  }
  if (!findJsonString(json, len, "emotion", out.emotion, sizeof(out.emotion), nullptr)) {
    return false;
  }
  
  if (!findJsonFloat(json, len, "expression_intensity", &out.expression_intensity)) {
    out.expression_intensity = 1.0f;
  }
  
  if (out.expression_intensity < 0.0f) out.expression_intensity = 0.0f;
  if (out.expression_intensity > 1.0f) out.expression_intensity = 1.0f;
  
  if (!findJsonString(json, len, "animation_hint", out.animation_hint, sizeof(out.animation_hint), nullptr)) {
  }
  
  StringSpan audioSpan = extractJsonStringSpan(json, len, "audio_wav_b64");
  if (audioSpan.ptr && audioSpan.len > 0) {
    size_t estDecodedLen = (audioSpan.len * 3) / 4;
    out.wav = static_cast<uint8_t*>(heap_caps_malloc(estDecodedLen, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (out.wav) {
      out.wav_len = decodeBase64(audioSpan.ptr, audioSpan.len, out.wav, estDecodedLen);
      out.has_audio = (out.wav_len > 0);
      if (!out.has_audio && out.wav) {
        heap_caps_free(out.wav);
        out.wav = nullptr;
        out.wav_len = 0;
      }
    }
  } else {
    out.has_audio = false;
  }
  
  const char* actionJson;
  size_t actionLen;
  if (findJsonObject(json, len, "action", &actionJson, &actionLen)) {
    parseActionFields(actionJson, actionLen, 
                      out.action_type, sizeof(out.action_type),
                      out.action_text, sizeof(out.action_text),
                      &out.action_level, &out.action_ms);
  } else {
    strncpy(out.action_type, "none", sizeof(out.action_type) - 1);
    out.action_level = 0;
    out.action_ms = 0;
  }
  
  out.parse_ok = true;
  return true;
}

void freeGatewayResponseAudio(GatewayResponse& resp) {
  if (resp.wav) {
    heap_caps_free(resp.wav);
    resp.wav = nullptr;
  }
  resp.wav_len = 0;
  resp.has_audio = false;
}

void freeGatewayResponseAudio(const GatewayResponse& resp) {
  (void)resp;
}

}  // namespace aura
