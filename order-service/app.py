print("Order Service")
"""
SecureShop - Order Service (minimal)
Handles: cart management, order lifecycle
"""

import os
import sqlite3
import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "orders.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'pending',
            total      REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity   INTEGER NOT NULL,
            price      REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_user_id():
    return request.headers.get("X-User-Id", "anonymous")


@app.post("/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    user_id = get_user_id()
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "items are required"}), 400

    total = sum(i.get("price", 0) * i.get("quantity", 1) for i in items)
    created_at = datetime.datetime.utcnow().isoformat()

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO orders (user_id, status, total, created_at) VALUES (?, ?, ?, ?)",
        (user_id, "pending", total, created_at)
    )
    order_id = cur.lastrowid

    for item in items:
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
            (order_id, item.get("product_id", 0), item.get("quantity", 1), item.get("price", 0))
        )

    conn.commit()
    conn.close()
    return jsonify({"order_id": order_id, "status": "pending", "total": total}), 201


@app.get("/orders")
def list_orders():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM orders WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/orders/<int:order_id>")
def get_order(order_id: int):
    conn = get_db()
    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?", (order_id,)
    ).fetchone()

    if not order:
        return jsonify({"error": "Order not found"}), 404

    items = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    conn.close()

    result = dict(order)
    result["items"] = [dict(i) for i in items]
    return jsonify(result), 200


@app.patch("/orders/<int:order_id>/status")
def update_status(order_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status", "")

    if status not in ("pending", "confirmed", "shipped", "delivered", "cancelled"):
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db()
    conn.execute(
        "UPDATE orders SET status = ? WHERE id = ?", (status, order_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"order_id": order_id, "status": status}), 200


@app.delete("/orders/<int:order_id>")
def cancel_order(order_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Order cancelled"}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "order-service"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8003, debug=True)
