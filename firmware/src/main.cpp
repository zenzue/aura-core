// AURA firmware - skeleton build validation
#include <M5Unified.h>

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    M5.Display.print("AURA skeleton OK");
}

void loop() {
    M5.update();
    delay(10);
}
