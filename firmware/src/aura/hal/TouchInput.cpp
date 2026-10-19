// TouchInput: M5.Touch polling, single-active-touch tracking, tap/pet/hold emission.
// Tap chain: single release posts TOUCH_TAP; >=3 taps within 900ms post TOUCH_PET;
// hold >=700ms posts HOLD_BEGIN then HOLD_END and resets the chain.

#include <aura/hal.h>
#include <aura/events.h>
#include <aura/log.h>
#include <M5Unified.h>

namespace aura {

class TouchInputImpl {
 public:
  void begin() {
    M5.Touch.setHoldThresh(700);
    _lastTapMs = 0;
    _tapChain = 0;
    _touchDownMs = 0;
    _wasTouchDown = false;
    _sentHoldBegin = false;
    _lastX = 0;
    _lastY = 0;
  }

  void update() {
    auto& touch = M5.Touch;
    const uint8_t count = touch.getCount();
    uint32_t now = millis();

    bool touching = false;
    int16_t x = _lastX, y = _lastY;
    if (count > 0) {
      const auto& d = touch.getDetail(0);
      touching = d.isPressed();
      x = static_cast<int16_t>(d.x);
      y = static_cast<int16_t>(d.y);
    }

    if (touching && !_wasTouchDown) {
      _wasTouchDown = true;
      _touchDownMs = now;
      _sentHoldBegin = false;
      _lastX = x;
      _lastY = y;
      post(EventKind::TOUCH_DOWN, x, y, 0);
    } else if (touching && _wasTouchDown && !_sentHoldBegin) {
      const uint32_t elapsed = now - _touchDownMs;
      if (elapsed >= 700) {
        _sentHoldBegin = true;
        post(EventKind::TOUCH_HOLD_BEGIN, x, y, 0);
      }
    } else if (!touching && _wasTouchDown) {
      const uint32_t duration = now - _touchDownMs;
      post(EventKind::TOUCH_UP, _lastX, _lastY, duration);

      const bool wasHold = _sentHoldBegin || duration >= 700;
      if (wasHold) {
        post(EventKind::TOUCH_HOLD_END, _lastX, _lastY, duration);
        _tapChain = 0;
        _lastTapMs = 0;
      } else {
        const uint32_t sinceLastTap = _lastTapMs ? (now - _lastTapMs) : 9999u;
        if (sinceLastTap <= 900) {
          _tapChain++;
        } else {
          if (_tapChain == 1) post(EventKind::TOUCH_TAP, _lastX, _lastY, 0);
          _tapChain = 1;
        }
        if (_tapChain >= 3) post(EventKind::TOUCH_PET, _lastX, _lastY, 0);
        _lastTapMs = now;
      }
      _wasTouchDown = false;
      _touchDownMs = 0;
      _sentHoldBegin = false;
    }
  }

 private:
  bool _wasTouchDown = false;
  bool _sentHoldBegin = false;
  uint32_t _touchDownMs = 0;
  uint32_t _lastTapMs = 0;
  uint8_t _tapChain = 0;
  int16_t _lastX = 0;
  int16_t _lastY = 0;

  static void post(EventKind kind, int16_t x, int16_t y, uint32_t param) {
    Event e{kind, x, y, param};
    EventBus::instance().post(e);
  }
};

static TouchInputImpl g_touchImpl;

void TouchInput::begin() { g_touchImpl.begin(); }
void TouchInput::update() { g_touchImpl.update(); }

}  // namespace aura
