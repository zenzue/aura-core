// Logging helpers. Use AURA_LOG for diagnostics only; NEVER log secrets.
#pragma once
#include <Arduino.h>
#ifndef AURA_LOG_LEVEL
#define AURA_LOG_LEVEL 1   // 0 off, 1 info+, 2 verbose
#endif
#if AURA_LOG_LEVEL
#define AURA_LOGF(fmt, ...) Serial.printf("[AURA] " fmt "\n", ##__VA_ARGS__)
#else
#define AURA_LOGF(fmt, ...)
#endif
#define AURA_LOGW(fmt, ...) Serial.printf("[AURA!W] " fmt "\n", ##__VA_ARGS__)
