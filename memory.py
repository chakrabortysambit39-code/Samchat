"""
memory.py
Lightweight persistent memory: recent conversation turns + arbitrary
key/value "facts" Jarvis is told to remember (e.g. "remember my wifi
password is X" -> facts['wifi password'] = 'X').
"""
import json
import os
from datetime import datetime

from config import MEMORY_FILE

MAX_HISTORY = 200


def _load() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {"history": [], "facts": {}}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("history", [])
            data.setdefault("facts", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"history": [], "facts": {}}


def _save(data: dict) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_turn(speaker: str, text: str) -> None:
    data = _load()
    data["history"].append({
        "speaker": speaker,
        "text": text,
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    data["history"] = data["history"][-MAX_HISTORY:]
    _save(data)


def get_history(limit: int = 20) -> list:
    return _load()["history"][-limit:]


def remember_fact(key: str, value: str) -> None:
    data = _load()
    data["facts"][key.strip().lower()] = value.strip()
    _save(data)


def recall_fact(key: str):
    return _load()["facts"].get(key.strip().lower())


def all_facts() -> dict:
    return _load()["facts"]


def forget_fact(key: str) -> bool:
    data = _load()
    key = key.strip().lower()
    if key in data["facts"]:
        del data["facts"][key]
        _save(data)
        return True
    return False


def clear_history() -> None:
    data = _load()
    data["history"] = []
    _save(data)
