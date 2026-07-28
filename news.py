"""
news.py
Headlines via Google News RSS (public, no API key). Falls back gracefully
if there's no internet connection.
"""
import xml.etree.ElementTree as ET

import requests

from utils import get_logger

log = get_logger("news")

RSS_URL = "https://news.google.com/rss"
RSS_TOPIC_URL = "https://news.google.com/rss/search?q={query}"


def get_top_headlines(country: str = "IN", limit: int = 5) -> list:
    """Return a list of headline strings."""
    try:
        params = {"hl": "en", "gl": country, "ceid": f"{country}:en"}
        r = requests.get(RSS_URL, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item")[:limit]
        return [item.findtext("title", default="").strip() for item in items if item.findtext("title")]
    except (requests.RequestException, ET.ParseError) as e:
        log.warning("news fetch failed: %s", e)
        return []


def search_news(topic: str, limit: int = 5) -> list:
    try:
        r = requests.get(RSS_TOPIC_URL.format(query=requests.utils.quote(topic)), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item")[:limit]
        return [item.findtext("title", default="").strip() for item in items if item.findtext("title")]
    except (requests.RequestException, ET.ParseError) as e:
        log.warning("news search failed: %s", e)
        return []


def format_headlines(headlines: list) -> str:
    if not headlines:
        return "I couldn't fetch the news right now — check your internet connection."
    return "Here are the top headlines:\n" + "\n".join(f"  {i+1}. {h}" for i, h in enumerate(headlines))
