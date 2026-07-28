"""
server.py
Web version of Jarvis: FastAPI backend + a static browser chat UI
(static/index.html). Run it locally, or behind HTTPS -- see README for
both a quick self-signed cert (dev) and a real-domain/Let's Encrypt
setup (production).

    uvicorn server:app --host 0.0.0.0 --port 8443 \
        --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem

This is now a multi-user personal assistant: visitors create an
account (email + password) at /login, and each account's chat history
is kept in its own private folder under data/users/<id>/ (see
memory.py / users.py). Settings and reminders are still shared across
everyone for now (see README "Known limitations").
"""
import os

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import memory
import reminders
import settings
import users
from assistant import Assistant
from utils import get_logger

log = get_logger("server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

SESSION_COOKIE = "jarvis_session"

app = FastAPI(title="Jarvis AI")

# Same-origin by default (the UI is served from this app). CORS is only
# relevant if you point a separately-hosted front-end at this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# One shared Assistant instance for this process. speak_replies is left
# False here -- TTS in the web UI happens client-side via the browser's
# Web Speech API (see static/app.js), not the server-side pyttsx3 engine.
_assistant = Assistant(speak_replies=False)


# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------

def get_current_user(jarvis_session: str = Cookie(default=None)) -> str | None:
    """FastAPI dependency: returns the logged-in user's email, or None."""
    return users.get_session_user(jarvis_session)


def require_user(jarvis_session: str = Cookie(default=None)) -> str:
    """FastAPI dependency: returns the logged-in user's email, or raises
    401 if there's no valid session. Use this on any endpoint that
    should only work for a logged-in user."""
    email = users.get_session_user(jarvis_session)
    if not email:
        raise HTTPException(status_code=401, detail="not logged in")
    return email


class SignupIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


def _set_session_cookie(response, email: str) -> None:
    token = users.create_session(email)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=int(users.SESSION_TTL.total_seconds()),
        # secure=True,  # uncomment once you're serving over HTTPS
    )


@app.post("/api/auth/signup")
def auth_signup(payload: SignupIn):
    try:
        email = users.signup(payload.email, payload.password)
    except users.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    resp = JSONResponse({"email": email})
    _set_session_cookie(resp, email)
    return resp


@app.post("/api/auth/login")
def auth_login(payload: LoginIn):
    try:
        email = users.login(payload.email, payload.password)
    except users.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    resp = JSONResponse({"email": email})
    _set_session_cookie(resp, email)
    return resp


@app.post("/api/auth/logout")
def auth_logout(jarvis_session: str = Cookie(default=None)):
    if jarvis_session:
        users.destroy_session(jarvis_session)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/api/auth/me")
def auth_me(email: str = Depends(require_user)):
    return {"email": email}


# ---------------------------------------------------------------------
# Chat / vision / history -- all scoped to the logged-in user
# ---------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str


class SettingsIn(BaseModel):
    user_name: str | None = None
    assistant_name: str | None = None
    city: str | None = None
    news_country: str | None = None
    groq_api_key: str | None = None
    groq_model: str | None = None
    groq_vision_model: str | None = None
    openai_api_key: str | None = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn, email: str = Depends(require_user)):
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is empty")
    try:
        reply_text = _assistant.process(text, user=email)
    except Exception:
        log.exception("assistant.process failed")
        raise HTTPException(status_code=500, detail="internal error handling that message")
    return ChatOut(reply=reply_text)


MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB -- well under Groq's 20MB request limit


@app.post("/api/vision", response_model=ChatOut)
async def vision_analyze(
    image: UploadFile = File(...),
    prompt: str = Form(None),
    source: str = Form("image"),
    email: str = Depends(require_user),
):
    """Analyze an uploaded/captured image (file upload, browser webcam
    snapshot, or browser screen-capture frame -- all arrive here the
    same way as multipart form data)."""
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty image")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large (max 15MB)")
    try:
        reply_text = _assistant.process_image(data, prompt=prompt, source=source, user=email)
    except Exception:
        log.exception("assistant.process_image failed")
        raise HTTPException(status_code=500, detail="internal error analyzing that image")
    return ChatOut(reply=reply_text)


@app.get("/api/history")
def history(limit: int = 50, email: str = Depends(require_user)):
    return memory.get_history(limit=limit, user=email)


@app.get("/api/reminders")
def get_reminders(email: str = Depends(require_user)):
    # NOTE: reminders are still shared across all accounts for now --
    # scoping these per-user needs a look at reminders.py.
    return reminders.list_reminders()


@app.get("/api/settings")
def get_settings(email: str = Depends(require_user)):
    # NOTE: settings are still shared across all accounts for now --
    # scoping these per-user needs a look at config.py.
    cfg = settings.get_all()
    # never echo API keys back to the browser once saved
    for k in ("groq_api_key", "openai_api_key"):
        if cfg.get(k):
            cfg[k] = "••••••••" + cfg[k][-4:]
    return cfg


@app.post("/api/settings")
def update_settings(payload: SettingsIn, email: str = Depends(require_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None and v != ""}
    if updates:
        settings.set_many(**updates)
    return get_settings(email=email)


# ---------------------------------------------------------------------
# Static web UI
# ---------------------------------------------------------------------
# index.html (the chat UI) is gated behind login; login.html is not.
# app.js/style.css/etc. are served under /static so the login page and
# any pre-auth assets can load without a session.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/")
def index(request: Request, email: str | None = Depends(get_current_user)):
    if not email:
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.on_event("startup")
def _on_startup():
    reminders.rearm_pending()
    log.info("Jarvis web server started")
