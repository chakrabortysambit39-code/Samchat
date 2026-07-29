"""
ai.py
Fallback conversational layer used when commands.py can't match a known
intent. Works fully offline with simple rule-based small talk. If the
user supplies an OpenAI-compatible API key in settings, it's used for
richer replies instead — this is entirely optional, nothing here
requires an API key to function.
"""
import random
import re

import requests

import memory
import settings
from utils import get_logger

log = get_logger("ai")

_GREETING_RE = re.compile(r"\b(hi|hello|hey|yo|good morning|good evening|good afternoon)\b", re.IGNORECASE)
_THANKS_RE = re.compile(r"\b(thanks|thank you|thx|cheers)\b", re.IGNORECASE)
_HOWAREYOU_RE = re.compile(r"\bhow are you\b", re.IGNORECASE)
_NAME_RE = re.compile(r"\bwhat('?s| is) your name\b", re.IGNORECASE)
_BYE_RE = re.compile(r"\b(bye|goodbye|see you|exit|quit)\b", re.IGNORECASE)

_GREETINGS = ["Hey {name}, how can I help?", "Hi there! What do you need?", "Hello! I'm listening."]
_ACK = ["You're welcome!", "Anytime.", "Happy to help."]
_HOWAREYOU = ["Running smoothly, thanks for asking!", "All systems normal. How about you?"]
_UNKNOWN = [
    "I'm not sure how to help with that yet — try asking about weather, news, "
    "reminders, files, or opening apps and sites.",
    "I didn't quite catch an action there. I can check weather/news, set "
    "reminders, search or open things, and remember facts for you.",
]


def _rule_based_reply(text: str) -> str:
    name = settings.get("user_name", "there")
    if _BYE_RE.search(text):
        return "Goodbye!"
    if _GREETING_RE.search(text):
        return random.choice(_GREETINGS).format(name=name)
    if _THANKS_RE.search(text):
        return random.choice(_ACK)
    if _HOWAREYOU_RE.search(text):
        return random.choice(_HOWAREYOU)
    if _NAME_RE.search(text):
        return f"I'm {settings.get('assistant_name', 'Jarvis')}, your assistant."
    return random.choice(_UNKNOWN)


def _build_messages(text: str, user: str = None, conversation_id: str = None) -> list:
    history = memory.get_history(limit=10, user=user, conversation_id=conversation_id)
    messages = [{"role": "system",
                 "content": f"You are {settings.get('assistant_name', 'Jarvis')}, a concise, "
                            f"helpful assistant. Keep replies short."}]
    for turn in history:
        role = "user" if turn["speaker"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": text})
    return messages


def _call_openai_compatible(base_url: str, api_key: str, model: str, messages: list) -> str:
    r = requests.post(
        base_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": 300},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _llm_reply(text: str, user: str = None, conversation_id: str = None) -> str:
    """Try Groq first (fast, generous free tier), then a plain OpenAI key
    if that's configured instead, then fall back to offline rule-based
    small talk. A missing or bad key never breaks the app."""
    groq_key = settings.get("groq_api_key", "")
    openai_key = settings.get("openai_api_key", "")

    if not groq_key and not openai_key:
        return _rule_based_reply(text)

    messages = _build_messages(text, user=user, conversation_id=conversation_id)

    if groq_key:
        try:
            return _call_openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions",
                groq_key,
                settings.get("groq_model", "llama-3.3-70b-versatile"),
                messages,
            )
        except (requests.RequestException, KeyError, IndexError) as e:
            log.warning("Groq call failed: %s", e)

    if openai_key:
        try:
            return _call_openai_compatible(
                "https://api.openai.com/v1/chat/completions",
                openai_key,
                "gpt-4o-mini",
                messages,
            )
        except (requests.RequestException, KeyError, IndexError) as e:
            log.warning("OpenAI call failed: %s", e)

    return _rule_based_reply(text)


def reply(text: str, user: str = None, conversation_id: str = None) -> str:
    return _llm_reply(text, user=user, conversation_id=conversation_id)
