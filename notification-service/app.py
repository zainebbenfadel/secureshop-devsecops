"""
SecureShop - Notification Service
Handles: email/SMS dispatch (simulated), notification log
Port: 8005

No real email/SMS sent — all output goes to console + DB.
"""

import os
import sqlite3
import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "notifications.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT NOT NULL,
            type       TEXT NOT NULL,
            channel    TEXT NOT NULL,
            recipient  TEXT NOT NULL,
            subject    TEXT,
            message    TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'sent',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def send_email(recipient: str, subject: str, message: str):
    print(f"[EMAIL] To: {recipient} | Subject: {subject} | Body: {message}")


def send_sms(recipient: str, message: str):
    print(f"[SMS] To: {recipient} | Message: {message}")


@app.post("/notify")
def notify():
    data      = request.get_json(silent=True) or {}
    user_id   = data.get("user_id", "")
    ntype     = data.get("type", "general")
    channel   = data.get("channel", "email")
    recipient = data.get("recipient", "")
    subject   = data.get("subject", "Notification")
    message   = data.get("message", "")

    if not recipient or not message:
        return jsonify({"error": "recipient and message are required"}), 400
    if channel not in ("email", "sms"):
        return jsonify({"error": "channel must be email or sms"}), 400

    if channel == "email":
        send_email(recipient, subject, message)
    else:
        send_sms(recipient, message)

    created_at = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO notifications (user_id, type, channel, recipient, subject, message, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, ntype, channel, recipient, subject, message, "sent", created_at)
    )
    notif_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"notification_id": notif_id, "status": "sent"}), 201


@app.get("/notifications")
def list_notifications():
    user_id = request.args.get("user_id", "")
    conn = get_db()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ?", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM notifications").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.get("/notifications/<int:notif_id>")
def get_notification(notif_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM notifications WHERE id = ?", (notif_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify(dict(row)), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "notification-service"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8005, debug=True)