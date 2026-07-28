"""
voice.py
Speech-to-text via the `speech_recognition` package (Google's free web
API through that library — no key needed for light use). Falls back
gracefully if the package or a microphone isn't available.
"""
from utils import get_logger, safe_import

log = get_logger("voice")

_sr = safe_import("speech_recognition")


def is_available() -> bool:
    if _sr is None:
        return False
    try:
        _sr.Microphone.list_microphone_names()
        return True
    except Exception:
        return False


def listen(timeout: int = 5, phrase_time_limit: int = 10) -> str:
    """Listen on the default microphone and return recognized text, or
    '' if nothing could be understood / no mic is available."""
    if _sr is None:
        log.info("speech_recognition not installed; voice input disabled")
        return ""
    recognizer = _sr.Recognizer()
    try:
        with _sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        return recognizer.recognize_google(audio)
    except _sr.WaitTimeoutError:
        return ""
    except _sr.UnknownValueError:
        return ""
    except _sr.RequestError as e:
        log.warning("speech recognition service error: %s", e)
        return ""
    except OSError as e:
        log.warning("no microphone available: %s", e)
        return ""
