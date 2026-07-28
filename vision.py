"""
vision.py
Image understanding via Groq's vision-capable model (currently
qwen/qwen3.6-27b — see https://console.groq.com/docs/vision). Works with
raw image bytes from any source: a file upload, a webcam snapshot, or a
screen capture — they all funnel through analyze_image().

Requires a Groq API key (settings.get('groq_api_key')). There's no
meaningful offline fallback for "what's in this picture", so a missing
key returns a clear message instead of guessing.
"""
import base64

import requests

import settings
from utils import get_logger

log = get_logger("vision")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_PROMPT = "Describe what you see in this image in a couple of sentences."


def _guess_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # reasonable default; Groq is lenient


def analyze_image(image_bytes: bytes, prompt: str = DEFAULT_PROMPT) -> str:
    """Send image bytes + a text prompt to Groq's vision model, return
    the model's text reply. Never raises — returns a friendly error
    string instead so this can be called directly from a chat handler."""
    api_key = settings.get("groq_api_key", "")
    if not api_key:
        return ("I can't analyze images yet — add a Groq API key in Settings "
                 "(vision needs a real model, there's no offline fallback for this one).")

    mime = _guess_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    model = settings.get("groq_vision_model", "qwen/qwen3.6-27b")

    try:
        r = requests.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
                "max_completion_tokens": 500,
                "temperature": 0.4,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except requests.HTTPError as e:
        log.warning("Groq vision call failed: %s — %s", e, getattr(e.response, "text", ""))
        return "I couldn't analyze that image — the vision service returned an error."
    except (requests.RequestException, KeyError, IndexError) as e:
        log.warning("Groq vision call failed: %s", e)
        return "I couldn't reach the vision service right now — check your internet connection."
