#include <aura/events.h>

namespace aura {

EventBus& EventBus::instance() {
  static EventBus bus;
  return bus;
}

void EventBus::begin() {
  if (_q) return;
  _q = xQueueCreate(kEventQueueLen, sizeof(Event));
}

bool EventBus::post(const Event& e) {
  if (!_q) return false;
  if (xQueueSend(_q, &e, 0) == pdTRUE) return true;
  // queue full: drop OLDEST then insert
  if (xQueueReceive(_q, &_oldest_slot, 0) == pdTRUE) {
    _dropped++;
  }
  if (xQueueSend(_q, &e, 0) == pdTRUE) return true;
  _dropped++;
  return false;
}

bool EventBus::poll(Event& e, uint32_t timeout_ms) {
  if (!_q) return false;
  return xQueueReceive(_q, &e, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

}  // namespace aura
