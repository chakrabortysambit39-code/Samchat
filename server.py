"""
server.py
Web version of Jarvis: FastAPI backend + a static browser chat UI
(static/index.html). Run it locally, or behind HTTPS — see README for
both a quick self-signed cert (dev) and a real-domain/Let's Encrypt
setup (production).

    uvicorn server:app --host 0.0.0.0 --port 8443 \
        --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem

This is a single-user personal assistant, not a multi-tenant service:
there's no login system. If you expose it beyond your own machine, put
it behind a reverse proxy that adds authentication (e.g. Caddy with
basic auth, or a VPN/tailnet) — see README.
"""
import base64
import os
import secrets

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

import memory
import reminders
import settings
from assistant import Assistant
from utils import get_logger

log = get_logger("server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Jarvis AI")

# --------------------------------------------------------------------
# Basic auth: protects every route (static UI + all /api/* endpoints).
# Set APP_USERNAME / APP_PASSWORD in your environment (Render ->
# Environment tab). If either is unset, auth is skipped — useful for
# local dev, but make sure both are set in any public deployment.
# --------------------------------------------------------------------
APP_USERNAME = os.environ.get("APP_USERNAME")
APP_PASSWORD = os.environ.get("APP_PASSWORD")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not APP_USERNAME or not APP_PASSWORD:
            # Auth not configured — allow through (local/dev use).
            return await call_next(request)

        # Let uptime checks through without credentials.
        if request.url.path == "/api/health":
            return await call_next(request)

        auth = request.headers.get("authorization")
        if auth and auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
                user, _, pw = decoded.partition(":")
                if secrets.compare_digest(user, APP_USERNAME) and secrets.compare_digest(pw, APP_PASSWORD):
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Jarvis"'},
            content="Unauthorized",
        )


app.add_middleware(BasicAuthMiddleware)

# Same-origin by default (the UI is served from this app). CORS is only
# relevant if you point a separately-hosted front-end at this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# One shared Assistant instance for this process. speak_replies is left
# False here — TTS in the web UI happens client-side via the browser's
# Web Speech API (see static/app.js), not the server-side pyttsx3 engine.
_assistant = Assistant(speak_replies=False)


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
def chat(payload: ChatIn):
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is empty")
    try:
        reply_text = _assistant.process(text)
    except Exception:
        log.exception("assistant.process failed")
        raise HTTPException(status_code=500, detail="internal error handling that message")
    return ChatOut(reply=reply_text)


MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB — well under Groq's 20MB request limit


@app.post("/api/vision", response_model=ChatOut)
async def vision_analyze(image: UploadFile = File(...), prompt: str = Form(None), source: str = Form("image")):
    """Analyze an uploaded/captured image (file upload, browser webcam
    snapshot, or browser screen-capture frame — all arrive here the
    same way as multipart form data)."""
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty image")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large (max 15MB)")
    try:
        reply_text = _assistant.process_image(data, prompt=prompt, source=source)
    except Exception:
        log.exception("assistant.process_image failed")
        raise HTTPException(status_code=500, detail="internal error analyzing that image")
    return ChatOut(reply=reply_text)


@app.get("/api/history")
def history(limit: int = 50):
    return memory.get_history(limit=limit)


@app.get("/api/reminders")
def get_reminders():
    return reminders.list_reminders()


@app.get("/api/settings")
def get_settings():
    cfg = settings.get_all()
    # never echo API keys back to the browser once saved
    for k in ("groq_api_key", "openai_api_key"):
        if cfg.get(k):
            cfg[k] = "••••••••" + cfg[k][-4:]
    return cfg


@app.post("/api/settings")
def update_settings(payload: SettingsIn):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None and v != ""}
    if updates:
        settings.set_many(**updates)
    return get_settings()


# Static web UI — index.html served at "/", everything else (app.js,
# style.css) served under its own path. Mounted last so /api/* above
# takes priority.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.on_event("startup")
def _on_startup():
    reminders.rearm_pending()
    log.info("Jarvis web server started")
