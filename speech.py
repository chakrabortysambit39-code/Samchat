"""
speech.py
Text-to-speech. Uses pyttsx3 (offline, cross-platform) if it's installed;
otherwise falls back to silently no-op-ing so the rest of the app still
works on a machine without audio.
"""
import threading

from utils import get_logger, safe_import

log = get_logger("speech")

_pyttsx3 = safe_import("pyttsx3")
_engine = None
_engine_lock = threading.Lock()


def is_available() -> bool:
    return _pyttsx3 is not None


def _get_engine():
    global _engine
    if _engine is None and _pyttsx3 is not None:
        _engine = _pyttsx3.init()
    return _engine


def configure(rate: int = None, volume: float = None):
    engine = _get_engine()
    if not engine:
        return
    if rate is not None:
        engine.setProperty("rate", rate)
    if volume is not None:
        engine.setProperty("volume", volume)


def say(text: str, block: bool = False) -> None:
    """Speak `text`. Runs in a background thread by default so the GUI
    never freezes while Jarvis is talking."""
    if not text:
        return
    if not is_available():
        log.info("[voice unavailable, would say]: %s", text)
        return

    def _speak():
        with _engine_lock:
            engine = _get_engine()
            engine.say(text)
            engine.runAndWait()

    if block:
        _speak()
    else:
        t = threading.Thread(target=_speak, daemon=True)
        t.start()


def stop() -> None:
    engine = _get_engine()
    if engine:
        engine.stop()
