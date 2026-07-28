"""
config.py
Central place for file paths and persistent configuration (JSON on disk).
No API keys are required for the app to work out of the box.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")

DEFAULT_CONFIG = {
    "user_name": "there",
    "assistant_name": "Jarvis",
    "city": "Pune",
    "voice_enabled": True,
    "voice_rate": 175,
    "voice_volume": 1.0,
    "wake_word": "jarvis",
    "groq_api_key": "",         # optional: preferred LLM backend for chit-chat (fast + free tier)
    "groq_model": "llama-3.3-70b-versatile",
    "groq_vision_model": "qwen/qwen3.6-27b",  # Groq's current vision-capable model
    "openai_api_key": "",       # optional fallback if no Groq key is set
    "news_country": "in",
}


def load_config() -> dict:
    """Load config.json, creating it with defaults if missing. Environment
    variables (if set) take precedence over the file — this matters on
    Render/Heroku-style hosts where secrets belong in the dashboard's env
    vars, not a file that gets wiped on every redeploy."""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        cfg = dict(DEFAULT_CONFIG)
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(file_cfg)  # backfill any keys added in newer versions
        except (json.JSONDecodeError, OSError):
            save_config(DEFAULT_CONFIG)
            cfg = dict(DEFAULT_CONFIG)

    env_overrides = {
        "groq_api_key": os.environ.get("GROQ_API_KEY"),
        "groq_model": os.environ.get("GROQ_MODEL"),
        "groq_vision_model": os.environ.get("GROQ_VISION_MODEL"),
        "openai_api_key": os.environ.get("OPENAI_API_KEY"),
        "user_name": os.environ.get("JARVIS_USER_NAME"),
        "assistant_name": os.environ.get("JARVIS_ASSISTANT_NAME"),
        "city": os.environ.get("JARVIS_CITY"),
    }
    for key, val in env_overrides.items():
        if val:
            cfg[key] = val
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def update_config(**kwargs) -> dict:
    cfg = load_config()
    cfg.update(kwargs)
    save_config(cfg)
    return cfg
