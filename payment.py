"""
payments.py
UPI / Google Pay manual-approval payment flow for premium upgrade.

No payment gateway account needed — the user pays you directly via UPI,
then an admin manually approves the payment in the admin panel, which
flips the user's `premium` flag to True.

Flow:
  1. User clicks "Upgrade" -> POST /api/premium/create-order
  2. Server creates a pending order record + a upi:// deep link (opens Google Pay/PhonePe/etc.)
  3. User pays, then submits the UPI transaction ref via POST /api/premium/submit-txn
  4. Admin reviews pending orders in /admin, approves via POST /api/admin/payments/approve
  5. On approval, user.premium = True (and premium_since / premium_expires are set)
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Config — edit these for your setup
# ---------------------------------------------------------------------------

UPI_ID = os.environ.get("UPI_ID", "yourname@okhdfcbank")   # your real UPI ID
PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "Samchat")
PREMIUM_PRICE_INR = 200
PREMIUM_DURATION_DAYS = 30          # premium validity per payment
CURRENCY = "INR"

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
ORDERS_FILE = DATA_DIR / "orders.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Storage helpers (flat JSON file — swap for a real DB if you have one)
# ---------------------------------------------------------------------------

def _load_orders() -> dict:
    if not ORDERS_FILE.exists():
        return {}
    with open(ORDERS_FILE, "r") as f:
        return json.load(f)


def _save_orders(orders: dict) -> None:
    tmp = ORDERS_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(orders, f, indent=2)
    tmp.replace(ORDERS_FILE)


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

def create_order(user_id: str) -> dict:
    """Create a pending order and return its UPI deep link."""
    order_id = uuid.uuid4().hex[:10]
    note = f"Samchat Premium {order_id}"

    upi_link = (
        f"upi://pay?pa={quote(UPI_ID)}"
        f"&pn={quote(PAYEE_NAME)}"
        f"&am={PREMIUM_PRICE_INR}"
        f"&cu={CURRENCY}"
        f"&tn={quote(note)}"
    )

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "amount": PREMIUM_PRICE_INR,
        "status": "pending",          # pending -> submitted -> approved | rejected
        "created_at": time.time(),
        "upi_txn_ref": None,
        "note": note,
    }

    orders = _load_orders()
    orders[order_id] = order
    _save_orders(orders)

    return {"order_id": order_id, "upi_link": upi_link, "amount": PREMIUM_PRICE_INR, "note": note}


def submit_txn_ref(order_id: str, user_id: str, txn_ref: str) -> dict:
    """User confirms they paid and provides the UPI transaction reference."""
    orders = _load_orders()
    order = orders.get(order_id)

    if not order:
        raise ValueError("Order not found")
    if order["user_id"] != user_id:
        raise ValueError("Order does not belong to this user")
    if order["status"] not in ("pending", "submitted"):
        raise ValueError(f"Order already {order['status']}")

    order["upi_txn_ref"] = txn_ref.strip()
    order["status"] = "submitted"
    order["submitted_at"] = time.time()

    orders[order_id] = order
    _save_orders(orders)
    return order


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------

def list_pending_orders() -> list:
    orders = _load_orders()
    return [o for o in orders.values() if o["status"] in ("pending", "submitted")]


def approve_order(order_id: str) -> dict:
    orders = _load_orders()
    order = orders.get(order_id)
    if not order:
        raise ValueError("Order not found")

    order["status"] = "approved"
    order["approved_at"] = time.time()
    orders[order_id] = order
    _save_orders(orders)
    return order


def reject_order(order_id: str, reason: str = "") -> dict:
    orders = _load_orders()
    order = orders.get(order_id)
    if not order:
        raise ValueError("Order not found")

    order["status"] = "rejected"
    order["rejected_at"] = time.time()
    order["reject_reason"] = reason
    orders[order_id] = order
    _save_orders(orders)
    return order


def get_order(order_id: str) -> dict | None:
    return _load_orders().get(order_id)


def premium_expiry_from_now() -> float:
    return (datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)).timestamp()
