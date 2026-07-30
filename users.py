"""
users.py
Simple multi-user account system for the Jarvis web server.

Each user gets:
  - an entry in data/users.json (email -> {password_hash, salt, created})
  - a private folder data/users/<safe_id>/ for their memory + settings

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib hashlib, no extra
dependencies) -- never stored in plaintext.

Sessions are opaque random tokens kept in data/sessions.json with an
expiry, handed to the browser as an HttpOnly cookie. This is a
lightweight session store suitable for a personal/small-scale
deployment -- not meant to replace a real auth provider for a
multi-tenant SaaS product.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
USERS_DATA_DIR = os.path.join(DATA_DIR, "users")

SESSION_TTL = timedelta(days=30)
PBKDF2_ITERATIONS = 260_000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Raised for any user-facing signup/login failure."""


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(USERS_DATA_DIR, exist_ok=True)


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: str, data) -> None:
    _ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _load_users() -> dict:
    return _load_json(USERS_FILE, {})


def _save_users(users: dict) -> None:
    _save_json(USERS_FILE, users)


def _load_sessions() -> dict:
    return _load_json(SESSIONS_FILE, {})


def _save_sessions(sessions: dict) -> None:
    _save_json(SESSIONS_FILE, sessions)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _safe_id(email: str) -> str:
    """Filesystem-safe folder name derived from the email."""
    return re.sub(r"[^a-z0-9]+", "_", (email or "").strip().lower()).strip("_") or "user"


def user_data_dir(email: str) -> str:
    """Path to this user's private data folder, creating it if needed."""
    _ensure_dirs()
    path = os.path.join(USERS_DATA_DIR, _safe_id(email))
    os.makedirs(path, exist_ok=True)
    return path


def _hash_password(password: str, salt: bytes = None) -> tuple:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def signup(email: str, password: str) -> str:
    """Create a new account. Returns the normalized email.
    Raises AuthError if the email is invalid, already registered, or
    the password is too short."""
    email = _normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise AuthError("That doesn't look like a valid email address.")
    if len(password or "") < 8:
        raise AuthError("Password must be at least 8 characters.")

    users = _load_users()
    if email in users:
        raise AuthError("An account with that email already exists.")

    pw_hash, salt = _hash_password(password)
    users[email] = {
        "password_hash": pw_hash,
        "salt": salt,
        "created": datetime.now(timezone.utc).isoformat(),
        # premium / usage fields (see payments.py for the ₹200 upgrade flow)
        "premium": False,
        "premium_expires": None,   # unix timestamp, or None
        "usage_date": None,        # "YYYY-MM-DD" for the free daily counter
        "usage_count": 0,
    }
    _save_users(users)
    user_data_dir(email)  # create their private folder up front
    return email


def login(email: str, password: str) -> str:
    """Verify credentials. Returns the normalized email on success,
    raises AuthError on failure. Uses the same error message for
    'no such user' and 'wrong password' so login can't be used to
    enumerate registered emails."""
    email = _normalize_email(email)
    users = _load_users()
    record = users.get(email)
    if not record:
        raise AuthError("Incorrect email or password.")

    salt = bytes.fromhex(record["salt"])
    expected_hash, _ = _hash_password(password or "", salt)
    if not hmac.compare_digest(expected_hash, record["password_hash"]):
        raise AuthError("Incorrect email or password.")

    return email


def create_session(email: str) -> str:
    sessions = _load_sessions()
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "email": email,
        "expires": (datetime.now(timezone.utc) + SESSION_TTL).isoformat(),
    }
    _save_sessions(sessions)
    return token


def get_session_user(token: str):
    """Return the email tied to a session token, or None if missing/expired."""
    if not token:
        return None
    sessions = _load_sessions()
    record = sessions.get(token)
    if not record:
        return None
    expires = datetime.fromisoformat(record["expires"])
    if datetime.now(timezone.utc) > expires:
        del sessions[token]
        _save_sessions(sessions)
        return None
    return record["email"]


def destroy_session(token: str) -> None:
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)


# ---------------------------------------------------------------------
# Premium / usage helpers (₹200 UPI upgrade -- see payments.py)
# ---------------------------------------------------------------------

def get_user(email: str) -> dict | None:
    """Return the full user record (including premium/usage fields), or
    None if no such account. Adds an 'email' key for convenience."""
    email = _normalize_email(email)
    users = _load_users()
    record = users.get(email)
    if not record:
        return None
    record = dict(record)
    record["email"] = email
    return record


def save_user(record: dict) -> None:
    """Persist changes to a user record previously returned by get_user().
    Only the known mutable fields are written back; password_hash/salt/
    created are preserved as-is unless explicitly present in `record`."""
    email = _normalize_email(record.get("email", ""))
    if not email:
        raise ValueError("save_user: record has no email")

    users = _load_users()
    if email not in users:
        raise ValueError(f"save_user: no such account {email}")

    stored = users[email]
    for key, value in record.items():
        if key == "email":
            continue
        stored[key] = value
    users[email] = stored
    _save_users(users)


def is_premium(email: str) -> bool:
    """True if this account currently has an active premium upgrade."""
    import time
    record = get_user(email)
    if not record or not record.get("premium"):
        return False
    expires = record.get("premium_expires")
    return expires is None or expires > time.time()


def set_premium(email: str, expires_at: float) -> dict:
    """Activate premium for this account until `expires_at` (unix
    timestamp). Called by payments.py after an admin approves an
    order."""
    record = get_user(email)
    if not record:
        raise ValueError(f"set_premium: no such account {email}")
    record["premium"] = True
    record["premium_expires"] = expires_at
    save_user(record)
    return record


def check_and_increment_usage(email: str, daily_limit: int) -> bool:
    """Enforce the free-tier daily message limit for non-premium users.
    Returns True and increments the counter if the message is allowed.
    Returns False (without incrementing) if the user is out of free
    messages for today. Premium users always return True without
    touching the counter."""
    import time
    record = get_user(email)
    if not record:
        raise ValueError(f"check_and_increment_usage: no such account {email}")

    if is_premium(email):
        return True

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if record.get("usage_date") != today:
        record["usage_date"] = today
        record["usage_count"] = 0

    if record.get("usage_count", 0) >= daily_limit:
        return False

    record["usage_count"] = record.get("usage_count", 0) + 1
    save_user(record)
    return True


def get_usage(email: str, daily_limit: int) -> dict:
    """Read-only usage snapshot for the status badge, without incrementing."""
    record = get_user(email)
    if not record:
        raise ValueError(f"get_usage: no such account {email}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = record.get("usage_count", 0) if record.get("usage_date") == today else 0
    return {
        "premium": is_premium(email),
        "premium_expires": record.get("premium_expires"),
        "used_today": used,
        "daily_limit": daily_limit,
        "remaining": max(0, daily_limit - used),
    }
