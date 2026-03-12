import sqlite3
import datetime
import requests
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

DB_FILE = "eagle_drm.db"


def get_db_connection():
    return sqlite3.connect(DB_FILE)


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = cursor.fetchall()
    for col in cols:
        if col[1] == column_name:
            return True
    return False


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            ip_address TEXT,
            country TEXT,
            active_server TEXT,
            now_playing TEXT,
            device_model TEXT,
            last_seen TEXT,
            is_active INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0
        )
    """)

    if not column_exists(c, "devices", "expires_at"):
        c.execute("ALTER TABLE devices ADD COLUMN expires_at TEXT")

    conn.commit()
    conn.close()


def get_real_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    real_ip = request.headers.get("X-Real-IP", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if real_ip:
        return real_ip.strip()
    if cf_ip:
        return cf_ip.strip()
    return request.remote_addr or "Unknown"


def is_expired(expires_at):
    if not expires_at:
        return False
    try:
        exp = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
        return datetime.datetime.now() > exp
    except:
        try:
            exp = datetime.datetime.strptime(expires_at, "%Y-%m-%d")
            return datetime.datetime.now().date() > exp.date()
        except:
            return False


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "service": "eagle-server"})


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "healthy"})


@app.route("/api", methods=["GET"])
def heartbeat():
    device_id = request.args.get("device")
    server_name = request.args.get("server", "غير محدد")
    now_playing = request.args.get("playing", "يتصفح القوائم...")
    device_model = request.args.get("model", "غير معروف")

    if not device_id:
        return jsonify({"error": "No device ID"}), 400

    ip_address = get_real_ip()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT is_active, is_blocked, country, expires_at FROM devices WHERE device_id=?",
        (device_id,)
    )
    row = c.fetchone()

    is_active = 0
    is_blocked = 0
    country = "Unknown"
    expires_at = None

    if row:
        is_active = row[0]
        is_blocked = row[1]
        country = row[2]
        expires_at = row[3]
    else:
        try:
            if ip_address not in ["127.0.0.1", "::1", "Unknown"]:
                res = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=2).json()
                country = res.get("country", "Unknown")
            else:
                country = "Localhost"
        except:
            pass

    c.execute("""
        INSERT INTO devices (
            device_id, ip_address, country, active_server, now_playing,
            device_model, last_seen, is_active, is_blocked, expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            ip_address=excluded.ip_address,
            active_server=excluded.active_server,
            now_playing=excluded.now_playing,
            device_model=excluded.device_model,
            last_seen=excluded.last_seen
    """, (
        device_id, ip_address, country, server_name, now_playing,
        device_model, now, is_active, is_blocked, expires_at
    ))

    conn.commit()
    conn.close()

    if is_blocked:
        return jsonify({"status": "blocked", "action": "wipe_data"})
    elif is_expired(expires_at):
        return jsonify({"status": "expired"})
    elif not is_active:
        return jsonify({"status": "pending"})
    else:
        return jsonify({"status": "active"})


init_db()