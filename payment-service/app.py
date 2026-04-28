print("Payment Service")
"""
SecureShop - Payment Service (minimal)
Handles: payment initiation, transaction records
"""

import os
import sqlite3
import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "payments.db")


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
    return jsonify({"transaction_id": txn_id, "status": "completed"}), 200


@app.post("/payments/<int:txn_id>/refund")
def refund_payment(txn_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE transactions SET status = 'refunded' WHERE id = ?", (txn_id,)
    )
    conn.commit()
    conn.close()
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
