"""
browser.py
Open websites and run web/YouTube searches in the user's default browser.
"""
import webbrowser
from urllib.parse import quote_plus

from utils import get_logger

log = get_logger("browser")

SITE_SHORTCUTS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "wikipedia": "https://www.wikipedia.org",
    "maps": "https://maps.google.com",
}


def open_site(name_or_url: str) -> str:
    key = name_or_url.strip().lower()
    if key in SITE_SHORTCUTS:
        url = SITE_SHORTCUTS[key]
    elif key.startswith("http://") or key.startswith("https://"):
        url = name_or_url.strip()
    else:
        url = f"https://{name_or_url.strip()}"
    try:
        webbrowser.open(url)
        return f"Opening {name_or_url}."
    except Exception as e:
        log.warning("failed to open %s: %s", url, e)
        return f"I couldn't open {name_or_url}."


def search_web(query: str) -> str:
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    webbrowser.open(url)
    return f"Searching the web for '{query}'."


def search_youtube(query: str) -> str:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    webbrowser.open(url)
    return f"Searching YouTube for '{query}'."
