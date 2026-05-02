"""
SecureShop - Payment Service
Handles: payment initiation, transaction records
Port: 8004

Inter-service calls:
  - Calls order-service to update order status on payment completion
  - Calls inventory-service to deduct stock on confirmed payment
  - Calls notification-service to send payment receipts
"""

import os
import sqlite3
import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH               = os.environ.get("DB_PATH", "payments.db")
ORDER_SERVICE_URL     = os.environ.get("ORDER_SERVICE_URL", "http://order-service:8003")
INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://inventory-service:8006")
NOTIFICATION_SERVICE_URL = os.environ.get("NOTIFICATION_SERVICE_URL", "http://notification-service:8005")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            user_id    TEXT NOT NULL,
            amount     REAL NOT NULL,
            status     TEXT NOT NULL DEFAULT 'pending',
            method     TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_user_id():
    return request.headers.get("X-User-Id", "anonymous")


@app.post("/payments")
def initiate_payment():
    data     = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    amount   = data.get("amount")
    method   = data.get("method", "card")
    user_id  = get_user_id()

    if not order_id or not amount:
        return jsonify({"error": "order_id and amount are required"}), 400

    created_at = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO transactions (order_id, user_id, amount, status, method, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, user_id, amount, "pending", method, created_at)
    )
    txn_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"transaction_id": txn_id, "status": "pending"}), 201


@app.post("/payments/<int:txn_id>/confirm")
def confirm_payment(txn_id: int):
    conn = get_db()
    txn = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()

    if not txn:
        return jsonify({"error": "Transaction not found"}), 404

    conn.execute(
        "UPDATE transactions SET status = 'completed' WHERE id = ?", (txn_id,)
    )
    conn.commit()
    conn.close()

    order_id = txn["order_id"]
    user_id  = txn["user_id"]
    amount   = txn["amount"]

    # Update order status to confirmed
    try:
        requests.patch(
            f"{ORDER_SERVICE_URL}/orders/{order_id}/status",
            json={"status": "confirmed"},
            timeout=5
        )
    except requests.RequestException:
        pass

    # Fetch order items and deduct inventory
    try:
        resp = requests.get(
            f"{ORDER_SERVICE_URL}/orders/{order_id}",
            timeout=5
        )
        if resp.status_code == 200:
            order_data = resp.json()
            for item in order_data.get("items", []):
                requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/{item['product_id']}/deduct",
                    json={"quantity": item["quantity"]},
                    timeout=5
                )
    except requests.RequestException:
        pass

    # Send payment receipt notification
    try:
        requests.post(
            f"{NOTIFICATION_SERVICE_URL}/notify",
            json={
                "user_id":   user_id,
                "type":      "payment_confirmed",
                "channel":   "email",
                "recipient": f"{user_id}@example.com",
                "subject":   f"Payment Receipt - Order #{order_id}",
                "message":   f"Payment of ${amount:.2f} for order #{order_id} was successful. Transaction ID: {txn_id}",
            },
            timeout=5
        )
    except requests.RequestException:
        pass

    return jsonify({"transaction_id": txn_id, "status": "completed"}), 200


@app.post("/payments/<int:txn_id>/refund")
def refund_payment(txn_id: int):
    conn = get_db()
    txn = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    if not txn:
        return jsonify({"error": "Transaction not found"}), 404

    conn.execute(
        "UPDATE transactions SET status = 'refunded' WHERE id = ?", (txn_id,)
    )
    conn.commit()
    conn.close()

    # Update order to cancelled
    try:
        requests.patch(
            f"{ORDER_SERVICE_URL}/orders/{txn['order_id']}/status",
            json={"status": "cancelled"},
            timeout=5
        )
    except requests.RequestException:
        pass

    return jsonify({"transaction_id": txn_id, "status": "refunded"}), 200


@app.get("/payments")
def list_payments():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/payments/<int:txn_id>")
def get_payment(txn_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Transaction not found"}), 404
    return jsonify(dict(row)), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "payment-service"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8004, debug=True)