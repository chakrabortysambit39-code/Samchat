"""
memory.py
Multi-conversation memory for SamChat.

Each user has:

{
    "active": "<conversation id>",
    "facts": {},
    "conversations": [
        {
            "id": "...",
            "title": "...",
            "created": "...",
            "updated": "...",
            "history":[]
        }
    ]
}

Automatically migrates old memory.json files.
"""

import json
import os
import uuid
from datetime import datetime

from config import MEMORY_FILE

MAX_HISTORY = 200


def _memory_path(user=None):
    if not user:
        return MEMORY_FILE

    import users
    return os.path.join(users.user_data_dir(user), "memory.json")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _default():
    return {
        "active": None,
        "facts": {},
        "conversations": []
    }


def _load(user=None):

    path = _memory_path(user)

    if not os.path.exists(path):
        return _default()

    try:
        with open(path, "r", encoding="utf8") as f:
            data = json.load(f)
    except Exception:
        return _default()

    # migrate old format
    if "history" in data:

        conversation = {
            "id": uuid.uuid4().hex,
            "title": "Previous Chat",
            "created": _now(),
            "updated": _now(),
            "history": data.get("history", [])
        }

        return {
            "active": conversation["id"],
            "facts": data.get("facts", {}),
            "conversations": [conversation]
        }

    data.setdefault("facts", {})
    data.setdefault("active", None)
    data.setdefault("conversations", [])

    return data


def _save(data, user=None):

    path = _memory_path(user)

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2)


def list_conversations(user=None):

    data = _load(user)

    return sorted(
        data["conversations"],
        key=lambda c: c["updated"],
        reverse=True
    )


def create_conversation(title="New Chat", user=None):

    data = _load(user)

    conv = {
        "id": uuid.uuid4().hex,
        "title": title,
        "created": _now(),
        "updated": _now(),
        "history": []
    }

    data["conversations"].append(conv)
    data["active"] = conv["id"]

    _save(data, user)

    return conv


def set_active(conversation_id, user=None):

    data = _load(user)

    data["active"] = conversation_id

    _save(data, user)


def active_conversation(user=None):

    data = _load(user)

    cid = data["active"]

    if cid:

        for c in data["conversations"]:

            if c["id"] == cid:
                return c

    if not data["conversations"]:
        return create_conversation(user=user)

    data["active"] = data["conversations"][0]["id"]

    _save(data, user)

    return data["conversations"][0]


def get_history(limit=50, user=None, conversation_id=None):

    data = _load(user)

    if conversation_id:

        for c in data["conversations"]:
            if c["id"] == conversation_id:
                return c["history"][-limit:]

        return []

    return active_conversation(user)["history"][-limit:]


def add_turn(speaker, text, user=None, conversation_id=None):

    data = _load(user)

    if conversation_id:

        conv = None

        for c in data["conversations"]:
            if c["id"] == conversation_id:
                conv = c
                break

        if conv is None:

            conv = create_conversation(user=user)

            data = _load(user)

            for c in data["conversations"]:
                if c["id"] == conv["id"]:
                    conv = c
                    break

    else:

        conv = active_conversation(user)

        data = _load(user)

        for c in data["conversations"]:
            if c["id"] == conv["id"]:
                conv = c
                break

    conv["history"].append({
        "speaker": speaker,
        "text": text,
        "time": _now()
    })

    conv["history"] = conv["history"][-MAX_HISTORY:]

    conv["updated"] = _now()

    if (
        conv["title"] == "New Chat"
        and speaker.lower() == "user"
    ):
        conv["title"] = text[:40]

    _save(data, user)


def remember_fact(key, value, user=None):

    data = _load(user)

    data["facts"][key.lower()] = value

    _save(data, user)


def recall_fact(key, user=None):

    return _load(user)["facts"].get(key.lower())


def all_facts(user=None):

    return _load(user)["facts"]


def forget_fact(key, user=None):

    data = _load(user)

    if key.lower() in data["facts"]:

        del data["facts"][key.lower()]

        _save(data, user)

        return True

    return False


def clear_history(user=None, conversation_id=None):

    data = _load(user)

    if conversation_id:

        for c in data["conversations"]:

            if c["id"] == conversation_id:

                c["history"] = []
                c["updated"] = _now()

                break

    else:

        active = active_conversation(user)

        for c in data["conversations"]:

            if c["id"] == active["id"]:

                c["history"] = []
                c["updated"] = _now()

                break

    _save(data, user)
