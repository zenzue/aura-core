// EventBus: bounded FreeRTOS queue, fixed 12-byte events. Drop-oldest.
#pragma once
#include <aura/aura.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

namespace aura {

struct Event {
  EventKind kind;
  int16_t a;   // usually x / value
  int16_t b;   // usually y
  uint32_t param;
};

class EventBus {
 public:
  static EventBus& instance();
  void begin();
  bool post(const Event& e);                     // non-blocking; drops oldest on full
  bool poll(Event& e, uint32_t timeout_ms = 0);  // non-blocking by default
  uint32_t droppedCount() const { return _dropped; }

 private:
  EventBus() = default;
  QueueHandle_t _q = nullptr;
  uint32_t _dropped = 0;
  Event _oldest_slot;
};

}  // namespace aura
