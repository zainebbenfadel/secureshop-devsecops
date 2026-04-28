print("User Service")
"""
SecureShop - User Service (minimal)
Handles: registration, login, JWT issuance, profile
SAST target: Bandit

Intentional security issues for SAST demo:
  - B324: weak MD5 password hashing
  - B608: SQL string interpolation (SQLi vector)
  - B201: Flask debug=True
  - B105: JWT signature verification disabled
"""

import os
import sqlite3
import hashlib
import datetime
import jwt
from flask import Flask, request, jsonify

app = Flask(__name__)

# Bandit B105: hardcoded fallback secret
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-123")
DB_PATH = os.environ.get("DB_PATH", "users.db")


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'customer'
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    # Bandit B324: MD5 is cryptographically weak
    return hashlib.md5(password.encode()).hexdigest()  # noqa: S324


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email     = data.get("email", "").strip()
    password  = data.get("password", "")
    full_name = data.get("full_name", "").strip()

    if not email or not password or not full_name:
        return jsonify({"error": "email, password and full_name are required"}), 400

    pw_hash = hash_password(password)

    try:
        conn = get_db()
        # Bandit B608: raw string interpolation → SQL injection
        conn.execute(
            f"INSERT INTO users (email, password_hash, full_name) "
            f"VALUES ('{email}', '{pw_hash}', '{full_name}')"
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409

    return jsonify({"message": "User created"}), 201


@app.post("/login")
def login():
    data     = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    conn = get_db()
    # Bandit B608: SQL injection via f-string
    user = conn.execute(
        f"SELECT * FROM users WHERE email = '{email}'"
    ).fetchone()
    conn.close()

    if not user or user["password_hash"] != hash_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {
            "sub":   user["id"],
            "email": user["email"],
            "role":  user["role"],
            "exp":   datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        },
        SECRET_KEY,
        algorithm="HS256",
    )
    return jsonify({"access_token": token}), 200


@app.get("/profile")
def get_profile():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth[7:]
    try:
        # Bandit B105: signature verification disabled
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    user_id = payload.get("sub")
    conn = get_db()
    # Bandit B608: SQL injection in profile lookup
    user = conn.execute(
        f"SELECT id, email, full_name, role FROM users WHERE id = '{user_id}'"
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(dict(user)), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "user-service"}), 200


if __name__ == "__main__":
    init_db()
    # Bandit B201: debug=True exposes Werkzeug interactive debugger
    app.run(host="0.0.0.0", port=8001, debug=True)