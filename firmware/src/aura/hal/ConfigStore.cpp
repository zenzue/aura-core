// ConfigStore: NVS persistence for DeviceSettings.
//
// load(): Reads from NVS namespace "aura", fills defaults for missing keys.
// save(): Writes all fields to NVS, commits.
// factoryWipe(): Erases all keys in namespace, restores defaults.
//
// SECURITY: NEVER log secret values (token, wifiPass). Log only string lengths.

#include <aura/hal.h>
#include <aura/aura.h>
#include <aura/log.h>
#include <nvs_flash.h>

namespace aura {

using namespace cfgkeys;

class ConfigStoreImpl {
 public:
  bool load(DeviceSettings& s) {
    // Use defaults
    s = DeviceSettings{};  // brace init clears to defaults

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NS, NVS_READONLY, &handle);
    if (err != ESP_OK) {
      AURA_LOGF("ConfigStore NVS open failed: %s", esp_err_to_name(err));
      return false;
    }

    // pet_name
    {
      char buf[24];
      size_t len = sizeof(buf);
      if (nvs_get_str(handle, PET_NAME, buf, &len) == ESP_OK && len < sizeof(buf)) {
        memcpy(s.petName, buf, len);
        s.petName[len] = '\0';
      }
    }

    // gateway_url
    {
      char buf[64];
      size_t len = sizeof(buf);
      if (nvs_get_str(handle, GATEWAY_URL, buf, &len) == ESP_OK && len < sizeof(buf)) {
        memcpy(s.gatewayUrl, buf, len);
        s.gatewayUrl[len] = '\0';
      }
    }

    // wifi_ssid
    {
      char buf[33];
      size_t len = sizeof(buf);
      if (nvs_get_str(handle, WIFI_SSID, buf, &len) == ESP_OK && len < sizeof(buf)) {
        memcpy(s.wifiSsid, buf, len);
        s.wifiSsid[len] = '\0';
      }
    }

    // wifi_pass - do NOT log content
    {
      char buf[65];
      size_t len = sizeof(buf);
      if (nvs_get_str(handle, WIFI_PASS, buf, &len) == ESP_OK && len < sizeof(buf)) {
        memcpy(s.wifiPass, buf, len);
        s.wifiPass[len] = '\0';
        AURA_LOGF("ConfigStore loaded wifiPass: len=%zu", len);  // only log length
      }
    }

    // volume
    {
      uint8_t v;
      if (nvs_get_u8(handle, VOLUME, &v) == ESP_OK) {
        s.volume = v;
      }
    }

    // brightness
    {
      uint8_t b;
      if (nvs_get_u8(handle, BRIGHTNESS, &b) == ESP_OK) {
        s.brightness = b;
      }
    }

    // quiet_start
    {
      uint8_t q;
      if (nvs_get_u8(handle, QUIET_START, &q) == ESP_OK) {
        s.quietStart = q;
      }
    }

    // quiet_end
    {
      uint8_t q;
      if (nvs_get_u8(handle, QUIET_END, &q) == ESP_OK) {
        s.quietEnd = q;
      }
    }

    // flags
    {
      uint32_t f;
      if (nvs_get_u32(handle, FLAGS, &f) == ESP_OK) {
        s.flags = f;
      }
    }

    // token - do NOT log content
    {
      char buf[65];
      size_t len = sizeof(buf);
      if (nvs_get_str(handle, DEV_TOKEN, buf, &len) == ESP_OK && len < sizeof(buf)) {
        // Read but do not store in DeviceSettings (device-specific)
        // If you need a device token field, add to DeviceSettings struct
        AURA_LOGF("ConfigStore loaded devToken: len=%zu", len);
      }
    }

    nvs_close(handle);
    AURA_LOGF("ConfigStore load complete: name=%.24s vol=%u bright=%u", s.petName, s.volume, s.brightness);
    return true;
  }

  bool save(const DeviceSettings& s) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
      AURA_LOGF("ConfigStore NVS open (rw) failed: %s", esp_err_to_name(err));
      return false;
    }

    // pet_name (max 23 chars + null)
    char petNameBuf[24];
    memcpy(petNameBuf, s.petName, 23);
    petNameBuf[23] = '\0';
    err = nvs_set_str(handle, PET_NAME, petNameBuf);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set pet_name failed: %s", esp_err_to_name(err));
    }

    // gateway_url (max 63 chars + null)
    char gwBuf[64];
    memcpy(gwBuf, s.gatewayUrl, 63);
    gwBuf[63] = '\0';
    err = nvs_set_str(handle, GATEWAY_URL, gwBuf);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set gateway_url failed: %s", esp_err_to_name(err));
    }

    // wifi_ssid (max 32 chars + null)
    char ssidBuf[33];
    memcpy(ssidBuf, s.wifiSsid, 32);
    ssidBuf[32] = '\0';
    err = nvs_set_str(handle, WIFI_SSID, ssidBuf);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set wifi_ssid failed: %s", esp_err_to_name(err));
    }

    // wifi_pass (max 64 chars + null) - do NOT log value
    char passBuf[65];
    memcpy(passBuf, s.wifiPass, 64);
    passBuf[64] = '\0';
    err = nvs_set_str(handle, WIFI_PASS, passBuf);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set wifi_pass failed: %s", esp_err_to_name(err));
    }

    // volume
    err = nvs_set_u8(handle, VOLUME, s.volume);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set volume failed: %s", esp_err_to_name(err));
    }

    // brightness
    err = nvs_set_u8(handle, BRIGHTNESS, s.brightness);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set brightness failed: %s", esp_err_to_name(err));
    }

    // quiet_start
    err = nvs_set_u8(handle, QUIET_START, s.quietStart);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set quiet_start failed: %s", esp_err_to_name(err));
    }

    // quiet_end
    err = nvs_set_u8(handle, QUIET_END, s.quietEnd);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set quiet_end failed: %s", esp_err_to_name(err));
    }

    // flags
    err = nvs_set_u32(handle, FLAGS, s.flags);
    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore set flags failed: %s", esp_err_to_name(err));
    }

    // Commit
    err = nvs_commit(handle);
    nvs_close(handle);

    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore commit failed: %s", esp_err_to_name(err));
      return false;
    }

    AURA_LOGF("ConfigStore saved: name=%.24s vol=%u bright=%u", s.petName, s.volume, s.brightness);
    return true;
  }

  bool factoryWipe() {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
      AURA_LOGF("ConfigStore NVS open (rw) for wipe failed: %s", esp_err_to_name(err));
      return false;
    }

    err = nvs_erase_all(handle);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
      AURA_LOGW("ConfigStore erase_all failed: %s", esp_err_to_name(err));
    }

    err = nvs_commit(handle);
    nvs_close(handle);

    if (err != ESP_OK) {
      AURA_LOGW("ConfigStore commit after wipe failed: %s", esp_err_to_name(err));
      return false;
    }

    AURA_LOGF("ConfigStore factory wiped");
    return true;
  }
};

static ConfigStoreImpl g_storeImpl;

bool ConfigStore::load(DeviceSettings& s) {
  return g_storeImpl.load(s);
}

bool ConfigStore::save(const DeviceSettings& s) {
  return g_storeImpl.save(s);
}

bool ConfigStore::factoryWipe() {
  return g_storeImpl.factoryWipe();
}

}  // namespace aura
