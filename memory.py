"""
memory.py
Lightweight persistent memory: recent conversation turns + arbitrary
key/value "facts" Jarvis is told to remember (e.g. "remember my wifi
password is X" -> facts['wifi password'] = 'X').

Every function now takes an optional `user` (email) argument. When a
user is given, their history/facts live in that user's private data
folder (via users.user_data_dir), so different accounts never see
each other's data. When user is omitted, everything falls back to the
original single shared MEMORY_FILE from config.py -- so any caller
that hasn't been updated to pass a user keeps working exactly as
before.
"""
import json
import os
from datetime import datetime

from config import MEMORY_FILE

MAX_HISTORY = 200


def _memory_path(user: str = None) -> str:
    if not user:
        return MEMORY_FILE
    import users  # imported lazily to avoid a circular import at module load
    return os.path.join(users.user_data_dir(user), "memory.json")


def _load(user: str = None) -> dict:
    path = _memory_path(user)
    if not os.path.exists(path):
        return {"history": [], "facts": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("history", [])
            data.setdefault("facts", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"history": [], "facts": {}}


def _save(data: dict, user: str = None) -> None:
    with open(_memory_path(user), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_turn(speaker: str, text: str, user: str = None) -> None:
    data = _load(user)
    data["history"].append({
        "speaker": speaker,
        "text": text,
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    data["history"] = data["history"][-MAX_HISTORY:]
    _save(data, user)


def get_history(limit: int = 20, user: str = None) -> list:
    return _load(user)["history"][-limit:]


def remember_fact(key: str, value: str, user: str = None) -> None:
    data = _load(user)
    data["facts"][key.strip().lower()] = value.strip()
    _save(data, user)


def recall_fact(key: str, user: str = None):
    return _load(user)["facts"].get(key.strip().lower())


def all_facts(user: str = None) -> dict:
    return _load(user)["facts"]


def forget_fact(key: str, user: str = None) -> bool:
    data = _load(user)
    key = key.strip().lower()
    if key in data["facts"]:
        del data["facts"][key]
        _save(data, user)
        return True
    return False


def clear_history(user: str = None) -> None:
    data = _load(user)
    data["history"] = []
    _save(data, user)
