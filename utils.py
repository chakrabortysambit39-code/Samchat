"""
utils.py
Small shared helpers: logging setup and safe-import wrapper.
"""
import logging
import os
import sys

from config import DATA_DIR

LOG_FILE = os.path.join(DATA_DIR, "jarvis.log")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                             datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


def safe_import(module_name: str):
    """Import a module, returning None instead of raising if it's missing.
    Used for optional dependencies like pyttsx3 / speech_recognition so the
    rest of the app still runs on a machine without a mic or speakers."""
    try:
        return __import__(module_name)
    except ImportError:
        return None


def clamp(value, low, high):
    return max(low, min(high, value))
