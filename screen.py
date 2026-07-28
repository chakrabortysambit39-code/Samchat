"""
screen.py
Grabs a screenshot for the desktop GUI's "what's on my screen" feature.
Uses Pillow's ImageGrab, which works natively on Windows and macOS; on
Linux it needs an X server (most desktops have one) — this degrades
gracefully with a clear message if it doesn't work on a given machine.
The web UI captures the screen client-side via getDisplayMedia instead.
"""
import io

from utils import get_logger

log = get_logger("screen")

try:
    from PIL import ImageGrab
    _available = True
except ImportError:
    _available = False


def is_available() -> bool:
    return _available


def capture_screen():
    """Return a screenshot as JPEG bytes, or None on failure."""
    if not _available:
        log.info("Pillow ImageGrab not available; screen capture disabled")
        return None
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as e:
        log.warning("screen capture failed: %s", e)
        return None
