"""
reminders.py
Timed reminders: "remind me to X in N minutes/hours" (relative) and
"remind me to X at 5pm" / "at 17:30" (absolute, today or tomorrow if
that time has already passed). Persisted to disk so the list survives
a restart — rearm_pending() re-arms any still-future reminders and
will correctly fire and notify, not just silently drop them.
"""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta

from config import REMINDERS_FILE
from utils import get_logger

log = get_logger("reminders")

_lock = threading.Lock()
_active_timers = {}
_notify_callback = None  # set by the GUI so fired reminders can pop a toast / speak


def set_notify_callback(fn) -> None:
    """Register a function(reminder_dict) to be called whenever ANY
    reminder fires, including ones re-armed after a restart. The GUI
    calls this once at startup."""
    global _notify_callback
    _notify_callback = fn


def _load() -> list:
    if not os.path.exists(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(reminders: list) -> None:
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, indent=2)


def list_reminders() -> list:
    return [r for r in _load() if not r.get("fired")]


def cancel_reminder(reminder_id: str) -> bool:
    with _lock:
        timer = _active_timers.pop(reminder_id, None)
        if timer:
            timer.cancel()
        reminders = _load()
        remaining = [r for r in reminders if r["id"] != reminder_id]
        found = len(remaining) != len(reminders)
        _save(remaining)
        return found


def _mark_fired_and_notify(reminder_id: str, on_fire=None) -> None:
    with _lock:
        reminders = _load()
        fired_reminder = None
        for r in reminders:
            if r["id"] == reminder_id:
                r["fired"] = True
                fired_reminder = r
        _save(reminders)
        _active_timers.pop(reminder_id, None)
    if fired_reminder is None:
        return
    log.info("reminder fired: %s", fired_reminder["text"])
    callback = on_fire or _notify_callback
    if callback:
        try:
            callback(fired_reminder)
        except Exception:
            log.exception("reminder notify callback failed")


def _arm_timer(reminder: dict, delay: float, on_fire=None) -> None:
    timer = threading.Timer(delay, _mark_fired_and_notify, args=(reminder["id"], on_fire))
    timer.daemon = True
    timer.start()
    with _lock:
        _active_timers[reminder["id"]] = timer


def add_reminder(text: str, when: datetime, on_fire=None) -> dict:
    """Schedule a reminder. `on_fire(reminder_dict)` is called when it fires;
    if omitted, the globally registered notify callback (see
    set_notify_callback) is used instead."""
    delay = max(0, (when - datetime.now()).total_seconds())
    reminder = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "time": when.isoformat(timespec="seconds"),
        "fired": False,
    }
    with _lock:
        reminders = _load()
        reminders.append(reminder)
        _save(reminders)

    _arm_timer(reminder, delay, on_fire)
    return reminder


def parse_relative_time(phrase: str):
    """Parse phrases like '10 minutes', '2 hours', '1 hour 30 minutes'.
    Returns a datetime or None if it can't be parsed."""
    phrase = phrase.lower()
    hours = re.search(r"(\d+)\s*hour", phrase)
    minutes = re.search(r"(\d+)\s*min", phrase)
    seconds = re.search(r"(\d+)\s*sec", phrase)
    if not (hours or minutes or seconds):
        return None
    delta = timedelta(
        hours=int(hours.group(1)) if hours else 0,
        minutes=int(minutes.group(1)) if minutes else 0,
        seconds=int(seconds.group(1)) if seconds else 0,
    )
    return datetime.now() + delta


def parse_absolute_time(phrase: str):
    """Parse phrases like 'at 5pm', 'at 17:30', 'at 5:30 pm tomorrow'.
    Returns a datetime (today if the time is still ahead, otherwise
    tomorrow), or None if it can't be parsed."""
    phrase = phrase.lower().strip()
    tomorrow = "tomorrow" in phrase
    phrase = phrase.replace("tomorrow", "").strip()

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", phrase)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)

    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None

    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def rearm_pending() -> None:
    """Call once at startup to re-arm any reminders still in the future,
    so they actually fire and notify (via the registered callback)
    instead of being silently dropped."""
    for r in list_reminders():
        when = datetime.fromisoformat(r["time"])
        delay = (when - datetime.now()).total_seconds()
        if delay > 0:
            _arm_timer(r, delay)
        else:
            # missed while the app was closed — fire immediately so the
            # user still finds out, rather than losing it silently
            _arm_timer(r, 0)
