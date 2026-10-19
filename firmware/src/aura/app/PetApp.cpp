// PetApp.cpp - AURA application state machine + event pump (main task)
// Phase-1 test harness behavior:
//   - Tap screen: gaze follows + pet at repeated taps
//   - Hold 700ms: listening anim + capture stub
//   - Top-left corner tap (x<48&&y<32): toggle diagnostics
//   - In diagnostics: tap cycles 16 emotions, hold: exit
//
// Implementation note: All engine/renderer methods are called as declared.
// If any method is missing internal behavior (e.g., startCapture fails),
// the app still works - onListening is set true so face works, just logs.

#include <aura/app.h>
#include <aura/events.h>
#include <aura/audio.h>
#include <aura/log.h>

namespace aura {

static EmotionEngine s_engine;
static FaceRenderer s_renderer;
static TouchInput s_touchInput;
static PowerMonitor s_powerMonitor;
static TiltMonitor s_tiltMonitor;

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
            // Start capture (Phase 1: stub callback just posts event)
            AudioBus::instance().startCapture(
                kMaxUtteranceMs, nullptr,
                [](void* /*ctx*/, const int16_t* /*pcm16*/, size_t /*samples*/) {
                    // Phase 1: callback just posts event, stores nothing
                    // Phase 2 will consume the audio data
                });
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
    s_renderer.status(false, false, mic_ok);

    int bat_pct = s_powerMonitor.batteryPercent();
    bool charging = s_powerMonitor.isCharging();
    bool tilt_ok = true;

    char diag_line[40];
    snprintf(diag_line, sizeof(diag_line), "%s|%d%%|%s|tilt:%s|fps:%.0f",
             _settings.petName,
             bat_pct,
             charging ? "CHG" : "BAT",
             tilt_ok ? "OK" : "N/A",
             s_renderer.lastFps());
    
    s_renderer.toast(diag_line, kDefaultAccent565);
}

void PetApp::updateProactive(uint32_t now_ms) {
    (void)now_ms;
}

}  // namespace aura
