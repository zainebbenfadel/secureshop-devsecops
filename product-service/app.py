print("Product Service")
"""
SecureShop - Product Service (minimal)
Handles: product catalogue, search, categories
SAST target: Bandit

Intentional security issues for SAST demo:
  - B608: SQL string interpolation in search (SQLi)
  - B506: yaml.load() without Loader (arbitrary code exec)
  - B201: Flask debug=True
  - B310: urllib open with user-supplied URL (SSRF vector)
"""

import os
import sqlite3
import yaml
import urllib.request
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "products.db")


# ── DB helpers ────────────────────────────────────────────────────────────────

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
    # Seed a few demo products
    conn.execute("""
        INSERT OR IGNORE INTO products (id, name, description, price, stock, category)
        VALUES
          (1, 'Laptop',     'A fast laptop',      999.99, 10, 'electronics'),
          (2, 'T-Shirt',    'Cotton t-shirt',        19.99,  50, 'clothing'),
          (3, 'Coffee Mug', 'Ceramic mug 300ml',      8.99, 100, 'kitchen'),
          (4, 'Headphones', 'Noise cancelling',     149.99,  20, 'electronics')
    """)
    conn.commit()
    conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/products")
def list_products():
    """Return all products, optionally filtered by category."""
    category = request.args.get("category", "").strip()
    conn = get_db()

    if category:
        # Bandit B608: SQL injection via string interpolation
        rows = conn.execute(
            f"SELECT * FROM products WHERE category = '{category}'"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products").fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/products/<int:product_id>")
def get_product(product_id: int):
    """Return a single product by ID."""
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
    """Full-text search across name and description."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "q parameter is required"}), 400

    conn = get_db()
    # Bandit B608: unsanitised query string injected into SQL LIKE clause
    rows = conn.execute(
        f"SELECT * FROM products WHERE name LIKE '%{query}%' "
        f"OR description LIKE '%{query}%'"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/categories")
def list_categories():
    """Return all distinct product categories."""
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products").fetchall()
    conn.close()
    return jsonify([r["category"] for r in rows]), 200


@app.post("/products/import")
def import_products():
    """
    Import products from a YAML payload.
    Bandit B506: yaml.load() without safe Loader allows arbitrary object execution.
    """
    raw = request.data.decode("utf-8")
    # Bandit B506: unsafe yaml.load()
    data = yaml.load(raw, Loader=yaml.Loader)  # noqa: S506

    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of products"}), 400

    conn = get_db()
    inserted = 0
    for item in data:
        conn.execute(
            "INSERT INTO products (name, description, price, stock, category) "
            "VALUES (?, ?, ?, ?, ?)",
            (item.get("name"), item.get("description"),
             item.get("price", 0), item.get("stock", 0), item.get("category", "general"))
        )
        inserted += 1
    conn.commit()
    conn.close()
    return jsonify({"imported": inserted}), 201


@app.get("/products/fetch-external")
def fetch_external():
    """
    Fetch product data from an external URL supplied by the caller.
    Bandit B310: urllib.request.urlopen with user-supplied URL → SSRF.
    """
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url parameter required"}), 400

    # Bandit B310: no URL validation before opening
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        content = resp.read(4096).decode("utf-8")

    return jsonify({"content": content}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "product-service"}), 200


if __name__ == "__main__":
    init_db()
    # Bandit B201: debug=True
    app.run(host="0.0.0.0", port=8002, debug=True)