"""
memory.py
Persistent memory for Jarvis.

Two layers:
  1. Legacy single-history mode (add_turn/get_history/clear_history) --
     unchanged, used by the CLI/voice loop and any caller that doesn't
     pass a `user`. Backward compatible with earlier versions.
  2. Conversation mode (list_conversations/create_conversation/
     get_conversation/add_message/rename_conversation/
     delete_conversation) -- used by the web server so each user can
     have multiple separate, nameable chats with a sidebar to switch
     between them, the same way this session's history works.

Facts (remember_fact/recall_fact/etc.) are still a flat per-user
key/value store, independent of which conversation you were in when
you told Jarvis to remember something.

Everything lives under a user's private folder (users.user_data_dir);
when a user is given, a one-time migration wraps any old memory.json
history into a conversation called "Migrated history" so nobody loses
data when upgrading to this version.
"""
import json
import os
import uuid
from datetime import datetime

from config import MEMORY_FILE

MAX_HISTORY = 200
_AUTO_TITLE_MAX = 48


# ---------------------------------------------------------------------
# Legacy single-history mode (unchanged behavior)
# ---------------------------------------------------------------------

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


def clear_history(user: str = None) -> None:
    data = _load(user)
    data["history"] = []
    _save(data, user)


# ---------------------------------------------------------------------
# Facts (shared across conversations, per-user)
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Conversation mode (used by the web server)
# ---------------------------------------------------------------------

def _conversations_path(user: str) -> str:
    import users
    return os.path.join(users.user_data_dir(user), "conversations.json")


def _migrate_legacy_history(user: str) -> dict:
    """One-time migration: earlier versions of the web server kept a
    single memory.json (history + facts) per user. Wrap that history
    into one 'Migrated history' conversation so upgrading doesn't lose
    anything. Returns the new conversations-mode data dict (does NOT
    delete the old memory.json -- it's left alone, just no longer the
    active store)."""
    legacy = _load(user)
    history = legacy.get("history", [])
    facts = legacy.get("facts", {})

    data = {"conversations": {}, "facts": facts}
    if history:
        conv_id = uuid.uuid4().hex[:12]
        data["conversations"][conv_id] = {
            "id": conv_id,
            "title": "Migrated history",
            "created": history[0].get("time") or datetime.now().isoformat(timespec="seconds"),
            "updated": history[-1].get("time") or datetime.now().isoformat(timespec="seconds"),
            "messages": history,
        }
    return data


def _load_conversations(user: str) -> dict:
    path = _conversations_path(user)
    if not os.path.exists(path):
        data = _migrate_legacy_history(user)
        _save_conversations(user, data)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("conversations", {})
            data.setdefault("facts", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"conversations": {}, "facts": {}}


def _save_conversations(user: str, data: dict) -> None:
    with open(_conversations_path(user), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_conversations(user: str) -> list:
    """Newest-first list of {id, title, created, updated, message_count} --
    everything the sidebar needs, without the full message bodies."""
    data = _load_conversations(user)
    convs = list(data["conversations"].values())
    convs.sort(key=lambda c: c.get("updated", ""), reverse=True)
    return [
        {
            "id": c["id"],
            "title": c.get("title") or "New chat",
            "created": c.get("created"),
            "updated": c.get("updated"),
            "message_count": len(c.get("messages", [])),
        }
        for c in convs
    ]


def create_conversation(user: str, title: str = None) -> str:
    data = _load_conversations(user)
    conv_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat(timespec="seconds")
    data["conversations"][conv_id] = {
        "id": conv_id,
        "title": title or "New chat",
        "created": now,
        "updated": now,
        "messages": [],
    }
    _save_conversations(user, data)
    return conv_id


def get_conversation(user: str, conv_id: str):
    """Full conversation dict (including messages), or None if it
    doesn't exist / doesn't belong to this user."""
    data = _load_conversations(user)
    return data["conversations"].get(conv_id)


def rename_conversation(user: str, conv_id: str, title: str) -> bool:
    data = _load_conversations(user)
    conv = data["conversations"].get(conv_id)
    if not conv:
        return False
    title = (title or "").strip()
    if title:
        conv["title"] = title
        _save_conversations(user, data)
    return True


def delete_conversation(user: str, conv_id: str) -> bool:
    data = _load_conversations(user)
    if conv_id in data["conversations"]:
        del data["conversations"][conv_id]
        _save_conversations(user, data)
        return True
    return False


def add_message(user: str, conv_id: str, speaker: str, text: str) -> dict:
    """Append a message to a conversation (creating it if the id is
    unknown -- defensive; normally the caller creates it up front via
    create_conversation). Auto-titles the conversation from the first
    user message if it's still untitled. Returns the updated
    conversation dict."""
    data = _load_conversations(user)
    conv = data["conversations"].get(conv_id)
    now = datetime.now().isoformat(timespec="seconds")
    if conv is None:
        conv = {"id": conv_id, "title": "New chat", "created": now, "updated": now, "messages": []}
        data["conversations"][conv_id] = conv

    conv["messages"].append({"speaker": speaker, "text": text, "time": now})
    conv["messages"] = conv["messages"][-MAX_HISTORY:]
    conv["updated"] = now

    if speaker == "user" and (not conv.get("title") or conv["title"] == "New chat"):
        title = text.strip().replace("\n", " ")
        if len(title) > _AUTO_TITLE_MAX:
            title = title[:_AUTO_TITLE_MAX].rstrip() + "\u2026"
        conv["title"] = title or "New chat"

    _save_conversations(user, data)
    return conv
