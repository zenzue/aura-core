"""Optional-dependency skips: modules requiring extra-only packages are ignored."""
import importlib.util

collect_ignore = []
for _fname, _mods in {
    "test_stt_tts.py": ["faster_whisper", "piper"],
}.items():
    if any(importlib.util.find_spec(m) is None for m in _mods):
        collect_ignore.append(_fname)
