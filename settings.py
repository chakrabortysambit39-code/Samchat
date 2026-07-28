"""
settings.py
User-facing preferences layered on top of config.py. Kept separate from
config.py so the GUI settings panel has one obvious place to read/write.
"""
from config import load_config, update_config


def get(key: str, default=None):
    return load_config().get(key, default)


def set(key: str, value) -> None:
    update_config(**{key: value})


def get_all() -> dict:
    return load_config()


def set_many(**kwargs) -> dict:
    return update_config(**kwargs)


def toggle_voice() -> bool:
    cfg = load_config()
    new_val = not cfg.get("voice_enabled", True)
    update_config(voice_enabled=new_val)
    return new_val
