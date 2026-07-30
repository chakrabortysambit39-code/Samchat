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
import hmac
import os

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import memory
import payments
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


# Admin key for the /admin payment-approval panel. Set this as a real
# secret in your environment -- e.g.
#   export SAMCHAT_ADMIN_KEY="something-long-and-random"
# Do NOT ship the default value to production.
ADMIN_KEY = os.environ.get("SAMCHAT_ADMIN_KEY", "change-me")


def require_admin(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> bool:
    """FastAPI dependency: gates every /api/admin/* route behind a
    shared-secret header. Raises 401/403 if missing or wrong."""
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="missing admin key")
    if not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="invalid admin key")
    return True


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
    conversation_id: str | None = None


class ChatOut(BaseModel):
    reply: str
    conversation_id: str
    title: str


class ConversationOut(BaseModel):
    id: str
    title: str
    created: str | None = None
    updated: str | None = None
    message_count: int = 0


class RenameIn(BaseModel):
    title: str


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

    if not users.check_and_increment_usage(email, payments.FREE_DAILY_LIMIT):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "free_limit_reached",
                "message": "You're out of free messages for today. Upgrade to premium for unlimited access.",
                "price_inr": payments.PREMIUM_PRICE_INR,
            },
        )

    conv_id = payload.conversation_id
    if not conv_id or not memory.get_conversation(email, conv_id):
        conv_id = memory.create_conversation(email)

    try:
        reply_text = _assistant.process(text, user=email, conversation_id=conv_id)
    except Exception:
        log.exception("assistant.process failed")
        raise HTTPException(status_code=500, detail="internal error handling that message")

    conv = memory.get_conversation(email, conv_id) or {}
    return ChatOut(reply=reply_text, conversation_id=conv_id, title=conv.get("title", "New chat"))


MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB -- well under Groq's 20MB request limit


@app.post("/api/vision", response_model=ChatOut)
async def vision_analyze(
    image: UploadFile = File(...),
    prompt: str = Form(None),
    source: str = Form("image"),
    conversation_id: str = Form(None),
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

    if not users.check_and_increment_usage(email, payments.FREE_DAILY_LIMIT):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "free_limit_reached",
                "message": "You're out of free messages for today. Upgrade to premium for unlimited access.",
                "price_inr": payments.PREMIUM_PRICE_INR,
            },
        )

    conv_id = conversation_id
    if not conv_id or not memory.get_conversation(email, conv_id):
        conv_id = memory.create_conversation(email)

    try:
        reply_text = _assistant.process_image(data, prompt=prompt, source=source, user=email, conversation_id=conv_id)
    except Exception:
        log.exception("assistant.process_image failed")
        raise HTTPException(status_code=500, detail="internal error analyzing that image")

    conv = memory.get_conversation(email, conv_id) or {}
    return ChatOut(reply=reply_text, conversation_id=conv_id, title=conv.get("title", "New chat"))


@app.get("/api/history")
def history(limit: int = 50, conversation_id: str = None, email: str = Depends(require_user)):
    # Legacy single-history endpoint, kept for backward compatibility.
    # The sidebar uses /api/conversations instead.
    return memory.get_history(limit=limit, user=email, conversation_id=conversation_id)


# ------------------------------------------------------------- conversations

@app.get("/api/conversations", response_model=list[ConversationOut])
def list_conversations_endpoint(email: str = Depends(require_user)):
    return memory.list_conversations(email)


@app.post("/api/conversations")
def new_conversation_endpoint(email: str = Depends(require_user)):
    conv_id = memory.create_conversation(email)
    return memory.get_conversation(email, conv_id)


@app.get("/api/conversations/{conv_id}")
def get_conversation_endpoint(conv_id: str, email: str = Depends(require_user)):
    conv = memory.get_conversation(email, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@app.patch("/api/conversations/{conv_id}")
def rename_conversation_endpoint(conv_id: str, payload: RenameIn, email: str = Depends(require_user)):
    ok = memory.rename_conversation(email, conv_id, payload.title)
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")
    return memory.get_conversation(email, conv_id)


@app.delete("/api/conversations/{conv_id}")
def delete_conversation_endpoint(conv_id: str, email: str = Depends(require_user)):
    ok = memory.delete_conversation(email, conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True}


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
# Premium (₹200 UPI upgrade) -- user-facing
# ---------------------------------------------------------------------

class SubmitTxnIn(BaseModel):
    order_id: str
    txn_ref: str


@app.post("/api/premium/create-order")
def premium_create_order(email: str = Depends(require_user)):
    return payments.create_order(user_id=email)


@app.post("/api/premium/submit-txn")
def premium_submit_txn(payload: SubmitTxnIn, email: str = Depends(require_user)):
    try:
        order = payments.submit_txn_ref(payload.order_id, email, payload.txn_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "submitted", "order": order}


@app.get("/api/premium/status")
def premium_status(email: str = Depends(require_user)):
    return users.get_usage(email, payments.FREE_DAILY_LIMIT)



# ---------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------

@app.get("/api/admin/dashboard")
def admin_dashboard(_: bool = Depends(require_admin)):
    pending = payments.list_pending_orders()
    return {
        "success": True,
        "stats": {
            "total_users": 0,
            "premium_users": 0,
            "free_users": 0,
            "pending_payments": len(pending),
            "approved_payments": 0,
            "total_revenue": 0,
            "today_messages": 0,
            "total_messages": 0
        }
    }

# ---------------------------------------------------------------------
# Admin -- payment approval (all gated behind require_admin)
# ---------------------------------------------------------------------

class ApprovePaymentIn(BaseModel):
    order_id: str


class RejectPaymentIn(BaseModel):
    order_id: str
    reason: str = ""


@app.get("/api/admin/payments/pending")
def admin_pending_payments(_: bool = Depends(require_admin)):
    return {"orders": payments.list_pending_orders()}


@app.post("/api/admin/payments/approve")
def admin_approve_payment(payload: ApprovePaymentIn, _: bool = Depends(require_admin)):
    try:
        order = payments.approve_order(payload.order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        users.set_premium(order["user_id"], payments.premium_expiry_from_now())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "approved", "order": order}


@app.post("/api/admin/payments/reject")
def admin_reject_payment(payload: RejectPaymentIn, _: bool = Depends(require_admin)):
    try:
        order = payments.reject_order(payload.order_id, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "rejected", "order": order}


@app.get("/admin")
def admin_page():
    # Auth happens client-side: admin.html prompts for the X-Admin-Key
    # and sends it on every /api/admin/* call above.
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


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
