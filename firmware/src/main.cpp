// AURA firmware entry point - Phase 1: app shell with PetApp
// Arduino entry: setup() boots the pet, loop() pumps events at ~30fps

#include <M5Unified.h>
#include <esp_flash.h>
#include <nvs_flash.h>
#include <aura/app.h>
#include <aura/log.h>

// Global PetApp instance (value member, no heap)
static aura::PetApp g_app;

void setup() {
    // Initialize Serial first (M5 config includes serial_baudrate)
    Serial.begin(115200);
    delay(50);

    // NVS init BEFORE M5.begin (esp_wifi/M5Unified may use NVS internally)
    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err != ESP_OK && nvs_err != ESP_ERR_NVS_NO_FREE_PAGES && nvs_err != ESP_ERR_NVS_NEW_VERSION_FOUND) {
        AURA_LOGF("NVS init warning: %s", esp_err_to_name(nvs_err));
    }

    // Configure M5Unified
    auto cfg = M5.config();
    cfg.internal_mic = true;
    cfg.internal_spk = true;
    cfg.serial_baudrate = 115200;
    
    M5.begin(cfg);

    // Post-init: display settings
    delay(200);
    
    // Load settings first (we need brightness value)
    aura::ConfigStore store;
    aura::DeviceSettings settings;
    store.load(settings);
    
    // Display config
    M5.Display.setBrightness(settings.brightness);
    M5.Display.setRotation(1);  // landscape 320x240

    // Boot the pet app (initializes all subsystems)
    g_app.boot();
}

void loop() {
    // Pump the application main loop
    g_app.tick();
    
    // Small delay to prevent watchdog and maintain ~66fps scheduler
    // Animation ticks at engine update cadence (~30fps effective)
    vTaskDelay(pdMS_TO_TICKS(15));
}
