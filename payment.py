"""
payments.py
UPI / Google Pay manual-approval payment flow for Samchat Premium.
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPI_ID = os.environ.get("UPI_ID", "yourname@okhdfcbank")
PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "Samchat")

PREMIUM_PRICE_INR = int(os.environ.get("PREMIUM_PRICE_INR", 200))
PREMIUM_DURATION_DAYS = int(os.environ.get("PREMIUM_DURATION_DAYS", 30))
CURRENCY = "INR"

# Daily usage limits
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", 20))
PREMIUM_DAILY_LIMIT = int(os.environ.get("PREMIUM_DAILY_LIMIT", 999999))

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
ORDERS_FILE = DATA_DIR / "orders.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Storage Helpers
# ---------------------------------------------------------------------------

def _load_orders() -> dict:
    if not ORDERS_FILE.exists():
        return {}

    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_orders(orders: dict) -> None:
    tmp = ORDERS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)
    tmp.replace(ORDERS_FILE)


# ---------------------------------------------------------------------------
# Premium Helpers
# ---------------------------------------------------------------------------

def premium_expiry_from_now() -> float:
    return (
        datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
    ).timestamp()


# ---------------------------------------------------------------------------
# Create Order
# ---------------------------------------------------------------------------

def create_order(user_id: str) -> dict:
    order_id = uuid.uuid4().hex[:10]
    note = f"Samchat Premium {order_id}"

    upi_link = (
        f"upi://pay"
        f"?pa={quote(UPI_ID)}"
        f"&pn={quote(PAYEE_NAME)}"
        f"&am={PREMIUM_PRICE_INR}"
        f"&cu={CURRENCY}"
        f"&tn={quote(note)}"
    )

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "amount": PREMIUM_PRICE_INR,
        "status": "pending",
        "created_at": time.time(),
        "upi_txn_ref": None,
        "note": note,
    }

    orders = _load_orders()
    orders[order_id] = order
    _save_orders(orders)

    return {
        "order_id": order_id,
        "upi_link": upi_link,
        "amount": PREMIUM_PRICE_INR,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Submit Transaction Reference
# ---------------------------------------------------------------------------

def submit_txn_ref(order_id: str, user_id: str, txn_ref: str) -> dict:
    orders = _load_orders()

    if order_id not in orders:
        raise ValueError("Order not found")

    order = orders[order_id]

    if order["user_id"] != user_id:
        raise ValueError("This order belongs to another user.")

    if order["status"] not in ("pending", "submitted"):
        raise ValueError(f"Order already {order['status']}")

    order["upi_txn_ref"] = txn_ref.strip()
    order["status"] = "submitted"
    order["submitted_at"] = time.time()

    orders[order_id] = order
    _save_orders(orders)

    return order


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def list_pending_orders() -> list:
    orders = _load_orders()

    return [
        order
        for order in orders.values()
        if order["status"] in ("pending", "submitted")
    ]


def approve_order(order_id: str) -> dict:
    orders = _load_orders()

    if order_id not in orders:
        raise ValueError("Order not found")

    order = orders[order_id]

    order["status"] = "approved"
    order["approved_at"] = time.time()

    orders[order_id] = order
    _save_orders(orders)

    return order


def reject_order(order_id: str, reason: str = "") -> dict:
    orders = _load_orders()

    if order_id not in orders:
        raise ValueError("Order not found")

    order = orders[order_id]

    order["status"] = "rejected"
    order["reject_reason"] = reason
    order["rejected_at"] = time.time()

    orders[order_id] = order
    _save_orders(orders)

    return order


# ---------------------------------------------------------------------------
# Get Order
# ---------------------------------------------------------------------------

def get_order(order_id: str):
    return _load_orders().get(order_id)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def order_exists(order_id: str) -> bool:
    return order_id in _load_orders()


def order_status(order_id: str):
    order = get_order(order_id)
    if not order:
        return None
    return order["status"]
