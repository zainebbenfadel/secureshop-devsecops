"""
SecureShop - Inventory Service
Handles: stock levels, reservation, release, deduction
Port: 8006
"""

import os
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "inventory.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER UNIQUE NOT NULL,
            stock      INTEGER NOT NULL DEFAULT 0,
            reserved   INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO inventory (product_id, stock, reserved)
        VALUES
          (1, 10,  0),
          (2, 50,  0),
          (3, 100, 0),
          (4, 20,  0)
    """)
    conn.commit()
    conn.close()


@app.get("/inventory")
def list_inventory():
    conn = get_db()
    rows = conn.execute("SELECT * FROM inventory").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/inventory/<int:product_id>")
def get_stock(product_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Product not found in inventory"}), 404
    return jsonify(dict(row)), 200


@app.post("/inventory/<int:product_id>/reserve")
def reserve_stock(product_id: int):
    data     = request.get_json(silent=True) or {}
    quantity = data.get("quantity", 0)
    if quantity <= 0:
        return jsonify({"error": "quantity must be greater than 0"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Product not found in inventory"}), 404

    available = row["stock"] - row["reserved"]
    if quantity > available:
        return jsonify({"error": "Insufficient stock", "available": available}), 409

    conn.execute(
        "UPDATE inventory SET reserved = reserved + ? WHERE product_id = ?",
        (quantity, product_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"product_id": product_id, "reserved": quantity, "status": "reserved"}), 200


@app.post("/inventory/<int:product_id>/release")
def release_stock(product_id: int):
    data     = request.get_json(silent=True) or {}
    quantity = data.get("quantity", 0)
    if quantity <= 0:
        return jsonify({"error": "quantity must be greater than 0"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Product not found in inventory"}), 404

    release_qty = min(quantity, row["reserved"])
    conn.execute(
        "UPDATE inventory SET reserved = reserved - ? WHERE product_id = ?",
        (release_qty, product_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"product_id": product_id, "released": release_qty, "status": "released"}), 200


@app.post("/inventory/<int:product_id>/deduct")
def deduct_stock(product_id: int):
    data     = request.get_json(silent=True) or {}
    quantity = data.get("quantity", 0)
    if quantity <= 0:
        return jsonify({"error": "quantity must be greater than 0"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Product not found in inventory"}), 404

    conn.execute(
        "UPDATE inventory SET stock = stock - ?, reserved = MAX(0, reserved - ?) "
        "WHERE product_id = ?",
        (quantity, quantity, product_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"product_id": product_id, "deducted": quantity, "status": "deducted"}), 200


@app.put("/inventory/<int:product_id>")
def set_stock(product_id: int):
    data  = request.get_json(silent=True) or {}
    stock = data.get("stock")
    if stock is None or stock < 0:
        return jsonify({"error": "valid stock value is required"}), 400

    conn = get_db()
    conn.execute("""
        INSERT INTO inventory (product_id, stock, reserved)
        VALUES (?, ?, 0)
        ON CONFLICT(product_id) DO UPDATE SET stock = excluded.stock
    """, (product_id, stock))
    conn.commit()
    conn.close()
    return jsonify({"product_id": product_id, "stock": stock}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "inventory-service"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8006, debug=True)