"""Skip optional-dependency test modules when their extras are not installed."""
import importlib.util

collect_ignore = []
if importlib.util.find_spec("piper") is None:
    collect_ignore.append("test_stt_tts.py")
