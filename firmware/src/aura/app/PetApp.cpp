// PetApp.cpp - AURA application state machine + event pump (main task)

#include <aura/app.h>
#include <aura/events.h>
#include <aura/audio.h>
#include <aura/log.h>
#include <aura/net.h>

namespace aura {

static EmotionEngine s_engine;
static FaceRenderer s_renderer;
static TouchInput s_touchInput;
static PowerMonitor s_powerMonitor;
static TiltMonitor s_tiltMonitor;

static constexpr size_t kMaxAudioSamples = 160000;
static int16_t* s_captureBuffer = nullptr;
static size_t s_captureLen = 0;

// Toast timeout (ms)
static constexpr uint32_t kToastDurationMs = 4000;
static constexpr uint32_t kDiagnosticsDrawIntervalMs = 500;
static constexpr uint32_t kProactiveCheckIntervalMs = 2000;
static constexpr uint32_t kBannerDurationMs = 1500;
static constexpr uint8_t kTouchCornerX = 48;
static constexpr uint8_t kTouchCornerY = 32;

void PetApp::boot() {
    _state = AppState::BOOT;

    // NVS already init in main.cpp; load settings
    ConfigStore store;
    if (!store.load(_settings)) {
        AURA_LOGF("ConfigStore load failed, using defaults");
    }

    // Begin EventBus
    EventBus::instance().begin();

    s_touchInput.begin();
    s_powerMonitor.begin();
    s_tiltMonitor.begin();

    // Begin renderer with brightness from settings
    s_renderer.begin(_settings.brightness);

    // Begin EmotionEngine (seed with micros for randomness)
    s_engine.begin(micros());

    // Initialize AudioBus (may fail on hardware without mic - log, continue)
    if (!AudioBus::instance().init()) {
        AURA_LOGW("AudioBus init failed (missing mic/hardware)");
    } else {
        AudioBus::instance().setVolume(_settings.volume);
    }

    // Apply initial emotion and theme
    s_engine.setEmotion(Emotion::NEUTRAL, 1.0f);
    s_engine.applyTheme(kDefaultBgTop565, kDefaultBgBottom565, 
                        kDefaultEyeCore565, kDefaultEyeEdge565, kDefaultAccent565);

    // Draw initial background from engine rig theme
    s_renderer.drawBackground(s_engine.rig().bgTop565, s_engine.rig().bgBottom565);

    // Show boot banner
    s_renderer.banner("AURA", kDefaultAccent565);
    _boot_banner_until_set = true;

    _gatewayClient.begin();
    _gatewayClient.setPowerMonitor(&s_powerMonitor);
    _wifiManager.begin(PetApp::onNetStatus);
    _wifi_init_done = true;

    // Initial render after banner delay handled in tick
    _state = AppState::FACE;

    AURA_LOGF("AURA boot complete: pet='%s' vol=%u bright=%u", 
              _settings.petName, _settings.volume, _settings.brightness);
}

void PetApp::tick() {
    uint32_t now_ms = millis();

    s_touchInput.update();
    s_powerMonitor.update();
    s_tiltMonitor.update();

    if (_wifi_init_done) {
        _wifiManager.update();
        _gatewayClient.update();
    }

    // Poll EventBus with timeout=0, drain fully each tick
    Event e;
    while (EventBus::instance().poll(e, 0)) {
        handleEvent(e);
    }

    // Show banner for initial duration then switch to background
    if (_boot_banner_until_set && (now_ms - _last_proactive_check) > kBannerDurationMs) {
        _boot_banner_until_set = false;
        s_renderer.drawBackground(s_engine.rig().bgTop565, s_engine.rig().bgBottom565);
        s_renderer.render(s_engine.rig());
    }

    // Update EmotionEngine (cheap, never sleeps)
    s_engine.onActivity();
    s_engine.update(now_ms);

    // Update proactive behavior check (keep minimal - engine.update handles internals)
    if (now_ms - _last_proactive_check >= kProactiveCheckIntervalMs) {
        updateProactive(now_ms);
        _last_proactive_check = now_ms;
    }

    // Render face from engine rig
    s_renderer.render(s_engine.rig());

    // Diagnostics render every 500ms if active
    if (_diag_mode && (now_ms - _last_diag_draw >= kDiagnosticsDrawIntervalMs)) {
        renderDiagnostics();
        _last_diag_draw = now_ms;
    }
}

void PetApp::handleEvent(const Event& e) {
    switch (e.kind) {
        case EventKind::TOUCH_TAP: {
            // In diagnostics: cycle emotions via setEmotion directly
            if (_diag_mode) {
                Emotion next_em = s_engine.emotion();
                if (s_engine.currentEmotionListForDiag(next_em)) {
                    s_engine.setEmotion(next_em, 1.0f);
                    s_engine.onActivity();
                }
                // Dwell handled by setEmotion trigger, no extra logic needed
            } else {
                // Normal mode: check for corner toggle
                if (e.a < kTouchCornerX && e.b < kTouchCornerY) {
                    toggleDiagnostics();
                } else {
                    // Eye gaze follows tap, trigger pet on repeated taps
                    s_engine.onTouchLookAt(static_cast<float>(e.a), static_cast<float>(e.b));
                }
            }
            break;
        }

        case EventKind::TOUCH_PET: {
            s_engine.onPet();
            s_engine.onActivity();
            s_powerMonitor.vibrate(90, 40);  // light vibration
            break;
        }

        case EventKind::TOUCH_DOWN:
        case EventKind::TOUCH_UP: {
            s_engine.onTouchLookAt(static_cast<float>(e.a), static_cast<float>(e.b));
            if (e.kind == EventKind::TOUCH_UP) {
                s_engine.onTouchEnd();
            }
            break;
        }

        case EventKind::TOUCH_HOLD_BEGIN: {
            s_engine.onListening(true);
            s_engine.onActivity();
            _capturing_audio = true;
            AudioBus::instance().startCapture(
                kMaxUtteranceMs, this, PetApp::onAudioCaptured);
            break;
        }

        case EventKind::TOUCH_HOLD_END: {
            s_engine.onListening(false);
            AudioBus::instance().abortCapture();
            break;
        }

        case EventKind::EMOTION_REQUEST: {
            s_engine.setEmotion(static_cast<Emotion>(e.param), 1.0f);
            break;
        }

        case EventKind::POWER_LOW: {
            s_engine.setEmotion(Emotion::SAD, 1.0f);
            break;
        }

        case EventKind::POWER_CHARGING: {
            s_engine.onWakeAck();
            s_powerMonitor.vibrate(40, 60);  // gentle confirm
            break;
        }

        case EventKind::IMU_TILT: {
            s_engine.onTilt(static_cast<float>(e.a) / 1000.0f,
                           static_cast<float>(e.b) / 1000.0f,
                           static_cast<float>(e.param) / 1000.0f);
            break;
        }

        case EventKind::AUDIO_SPEAK_DONE: {
            break;
        }

        case EventKind::AUDIO_ERROR: {
            s_renderer.toast("audio err", kDefaultAccent565);
            break;
        }

        // Phase 1: NET_* unused but keep branches compiling
        case EventKind::NET_ONLINE:
        case EventKind::NET_OFFLINE:
        case EventKind::GATEWAY_REACHABLE:
        case EventKind::GATEWAY_LOST:
        case EventKind::AUDIO_UTTERANCE_READY:
        case EventKind::AUDIO_SPEAK_BEGIN:
        case EventKind::BEHAVIOR_PROACTIVE:
        case EventKind::DIAG_PING:
        case EventKind::PTT_BEGIN:
        case EventKind::PTT_END:
        case EventKind::NONE:
        default:
            break;
    }
}

void PetApp::toggleDiagnostics() {
    _diag_mode = !_diag_mode;
    _state = _diag_mode ? AppState::DIAGNOSTICS : AppState::FACE;
    _last_diag_draw = 0;
    
    if (_diag_mode) {
        AURA_LOGF("Diagnostics ENABLED");
    } else {
        AURA_LOGF("Diagnostics DISABLED");
        s_renderer.toast(nullptr, 0);
    }
}

void PetApp::renderDiagnostics() {
    bool mic_ok = AudioBus::instance().micStateDbg() != 0;
    bool wifi_ok = _wifi_init_done && _wifiManager.isConnected();
    s_renderer.status(wifi_ok, _gatewayClient.isOnline(), mic_ok);

    int bat_pct = s_powerMonitor.batteryPercent();
    bool charging = s_powerMonitor.isCharging();
    bool tilt_ok = true;
    int rssi = _wifi_init_done ? _wifiManager.getRSSI() : 0;

    uint32_t now_ms = millis();
    if (_wifi_init_done && now_ms - _last_stats_ms > kStatsReportMs) {
      _last_stats_ms = now_ms;
      _gatewayClient.reportDeviceStats(bat_pct, charging, rssi);
    }

    char diag_line[50];
    snprintf(diag_line, sizeof(diag_line), "%s|%d%%|%s|rssi:%d|tilt:%s",
             _settings.petName,
             bat_pct,
             charging ? "CHG" : "BAT",
             rssi,
             tilt_ok ? "OK" : "N/A");
    
    s_renderer.toast(diag_line, kDefaultAccent565);
}

void PetApp::updateProactive(uint32_t now_ms) {
    (void)now_ms;
}

void PetApp::onNetStatus(const char* status_text, bool online) {
    AURA_LOGF("Net status: %s online=%d", status_text ? status_text : "null", online);
}

void PetApp::onAudioCaptured(void* ctx, const int16_t* pcm16, size_t samples) {
    PetApp* self = static_cast<PetApp*>(ctx);
    if (!self || !pcm16 || samples == 0) return;
    
    if (!s_captureBuffer) {
        s_captureBuffer = static_cast<int16_t*>(heap_caps_malloc(
            kMaxAudioSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    }
    if (!s_captureBuffer) return;
    
    size_t copyLen = samples < kMaxAudioSamples ? samples : kMaxAudioSamples;
    memcpy(s_captureBuffer, pcm16, copyLen * sizeof(int16_t));
    s_captureLen = copyLen;
    
    AURA_LOGF("Audio captured samples=%zu", copyLen);
    
    if (self->_gatewayClient.isOnline()) {
        self->_gatewayClient.interactAudio(s_captureBuffer, s_captureLen,
                                           PetApp::onGatewayInteract, self);
    } else {
        AURA_LOGF("Gateway offline, using local fallback");
        s_engine.onListening(false);
        s_engine.onPet();
    }
}

void PetApp::onGatewayInteract(void* ctx, const GatewayResponse* resp, bool ok) {
    PetApp* self = static_cast<PetApp*>(ctx);
    if (!self) return;
    
    self->_capturing_audio = false;
    s_engine.onListening(false);
    
    if (!ok || !resp || !resp->parse_ok) {
        AURA_LOGF("Gateway interact failed or invalid response");
        s_engine.onPet();
        return;
    }
    
    Emotion emotion;
    if (emotionFromString(resp->emotion, emotion)) {
        s_engine.setEmotion(emotion, resp->expression_intensity);
    }
    
    if (strcmp(resp->action_type, "vibrate") == 0 && resp->action_level > 0) {
        s_powerMonitor.vibrate(resp->action_level, 
                               resp->action_ms > 0 ? resp->action_ms : 100);
    }
    
    if (resp->has_audio && resp->wav && resp->wav_len > 0) {
        const size_t len = resp->wav_len;
        uint8_t* wav = static_cast<uint8_t*>(
            heap_caps_malloc(len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (wav) {
            memcpy(wav, resp->wav, len);
            // playWavAsync copies into its own slot before returning; the
            // caller frees its buffer once the call completes.
            if (!AudioBus::instance().playWavAsync(wav, len, nullptr, nullptr)) {
                AURA_LOGF("playWavAsync rejected len=%zu", len);
            }
            heap_caps_free(wav);
        } else {
            AURA_LOGW("playback alloc failed len=%zu", len);
        }
    }
    freeGatewayResponseAudio(*const_cast<GatewayResponse*>(resp));
    
    AURA_LOGF("Gateway response: emotion=%s intensity=%.2f action=%s",
              resp->emotion, resp->expression_intensity, resp->action_type);
}

}  // namespace aura
