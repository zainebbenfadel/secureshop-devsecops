"""
SecureShop - Product Service
Handles: product catalogue, search, categories
Port: 8002

Intentional SAST targets (Bandit):
  - B608: SQL injection in search/filter
  - B506: yaml.load() without safe Loader
  - B201: Flask debug=True
  - B310: urllib open with user-supplied URL (SSRF)
"""

import os
import sqlite3
import yaml
import urllib.request
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "products.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT,
            price       REAL NOT NULL,
            stock       INTEGER NOT NULL DEFAULT 0,
            category    TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO products (id, name, description, price, stock, category)
        VALUES
          (1, 'Laptop',     'A fast laptop',        999.99, 10,  'electronics'),
          (2, 'T-Shirt',    'Cotton t-shirt',         19.99, 50,  'clothing'),
          (3, 'Coffee Mug', 'Ceramic mug 300ml',       8.99, 100, 'kitchen'),
          (4, 'Headphones', 'Noise cancelling',       149.99, 20, 'electronics')
    """)
    conn.commit()
    conn.close()


@app.get("/products")
def list_products():
    category = request.args.get("category", "").strip()
    conn = get_db()
    if category:
        # B608: SQL injection
        rows = conn.execute(
            f"SELECT * FROM products WHERE category = '{category}'"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/products/<int:product_id>")
def get_product(product_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(dict(row)), 200


@app.get("/products/search")
def search_products():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "q parameter is required"}), 400
    conn = get_db()
    # B608: unsanitised query injected into LIKE clause
    rows = conn.execute(
        f"SELECT * FROM products WHERE name LIKE '%{query}%' "
        f"OR description LIKE '%{query}%'"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/categories")
def list_categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products").fetchall()
    conn.close()
    return jsonify([r["category"] for r in rows]), 200


@app.post("/products")
def create_product():
    data = request.get_json(silent=True) or {}
    name     = data.get("name", "").strip()
    desc     = data.get("description", "")
    price    = data.get("price", 0)
    stock    = data.get("stock", 0)
    category = data.get("category", "general")

    if not name or price <= 0:
        return jsonify({"error": "name and price are required"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO products (name, description, price, stock, category) VALUES (?, ?, ?, ?, ?)",
        (name, desc, price, stock, category)
    )
    conn.commit()
    product_id = cur.lastrowid
    conn.close()
    return jsonify({"product_id": product_id, "message": "Product created"}), 201


@app.post("/products/import")
def import_products():
    """B506: yaml.load() without safe Loader allows arbitrary code execution."""
    raw = request.data.decode("utf-8")
    data = yaml.load(raw, Loader=yaml.Loader)  # noqa: S506
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of products"}), 400
    conn = get_db()
    inserted = 0
    for item in data:
        conn.execute(
            "INSERT INTO products (name, description, price, stock, category) VALUES (?, ?, ?, ?, ?)",
            (item.get("name"), item.get("description"),
             item.get("price", 0), item.get("stock", 0), item.get("category", "general"))
        )
        inserted += 1
    conn.commit()
    conn.close()
    return jsonify({"imported": inserted}), 201


@app.get("/products/fetch-external")
def fetch_external():
    """B310: urllib.request.urlopen with user-supplied URL → SSRF."""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url parameter required"}), 400
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        content = resp.read(4096).decode("utf-8")
    return jsonify({"content": content}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "product-service"}), 200


if __name__ == "__main__":
    init_db()
    # B201: debug=True
    app.run(host="0.0.0.0", port=8002, debug=True)