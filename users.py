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
