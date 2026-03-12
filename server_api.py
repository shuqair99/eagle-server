import sqlite3
import datetime
import logging
from flask import Flask, request, jsonify, Response
from functools import wraps
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ======================
# ADMIN LOGIN
# ======================

ADMIN_USER = "shuqair99"
ADMIN_PASS = "@LoLo9975@"


def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS


def authenticate():
    return Response(
        "Login Required",
        401,
        {"WWW-Authenticate": 'Basic realm="Admin Login"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ======================
# SERVER CONFIG
# ======================

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

DB_FILE = "/tmp/eagle_drm.db"


def db():
    return sqlite3.connect(DB_FILE)


# ======================
# DATABASE
# ======================

def init_db():

    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE,
        server TEXT,
        model TEXT,
        ip TEXT,
        created_at TEXT,
        last_seen TEXT,
        is_active INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        expires_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# ======================
# EXPIRE CHECK
# ======================

def expired(date):

    if not date:
        return False

    return datetime.datetime.utcnow() > datetime.datetime.fromisoformat(date)


# ======================
# HOME
# ======================

@app.route("/")
def home():
    return "Eagle DRM Server Online"


# ======================
# API
# ======================

@app.route("/api")
def api():

    device = request.args.get("device")
    server = request.args.get("server")
    model = request.args.get("model")

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if not device:
        return jsonify({"error": "device missing"})

    conn = db()
    c = conn.cursor()

    c.execute(
        "SELECT is_active,is_blocked,expires_at FROM devices WHERE device_id=?",
        (device,)
    )

    row = c.fetchone()

    now = datetime.datetime.utcnow().isoformat()

    if not row:

        c.execute("""
        INSERT INTO devices(device_id,server,model,ip,created_at,last_seen)
        VALUES(?,?,?,?,?,?)
        """, (
            device,
            server,
            model,
            ip,
            now,
            now
        ))

        conn.commit()
        conn.close()

        return jsonify({"status": "pending"})

    is_active, is_blocked, exp = row

    c.execute(
        "UPDATE devices SET last_seen=? WHERE device_id=?",
        (now, device)
    )

    conn.commit()
    conn.close()

    if is_blocked:
        return jsonify({"status": "blocked", "action": "wipe_data"})

    if expired(exp):
        return jsonify({"status": "expired"})

    if not is_active:
        return jsonify({"status": "pending"})

    return jsonify({"status": "active"})


# ======================
# ADMIN DASHBOARD
# ======================

@app.route("/admin")
@requires_auth
def admin():

    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM devices ORDER BY id DESC")

    rows = c.fetchall()

    html = """
    <html>
    <head>
    <title>Eagle Admin</title>

    <style>

    body{
        background:#0f172a;
        font-family:Arial;
        color:white;
        padding:40px
    }

    table{
        border-collapse:collapse;
        width:100%
    }

    td,th{
        border:1px solid #1e293b;
        padding:10px;
        text-align:center
    }

    th{
        background:#1e293b
    }

    tr:hover{
        background:#1e293b
    }

    a{
        color:#38bdf8;
        text-decoration:none;
        font-weight:bold
    }

    h1{
        margin-bottom:20px
    }

    </style>

    </head>

    <body>

    <h1>Eagle DRM Dashboard</h1>

    <table>

    <tr>
    <th>ID</th>
    <th>Device</th>
    <th>Server</th>
    <th>Model</th>
    <th>IP</th>
    <th>Status</th>
    <th>Expire</th>
    <th>Last Seen</th>
    <th>Actions</th>
    </tr>
    """

    for r in rows:

        (
            id,
            device,
            server,
            model,
            ip,
            created,
            last,
            active,
            blocked,
            exp
        ) = r

        if blocked:
            status = "BLOCKED"
        elif active:
            status = "ACTIVE"
        else:
            status = "PENDING"

        html += f"""

        <tr>

        <td>{id}</td>
        <td>{device}</td>
        <td>{server}</td>
        <td>{model}</td>
        <td>{ip}</td>
        <td>{status}</td>
        <td>{exp if exp else "-"}</td>
        <td>{last}</td>

        <td>

        <a href='/activate?device={device}'>Activate</a> |

        <a href='/block?device={device}'>Block</a> |

        <a href='/extend?device={device}&days=30'>+30d</a>

        </td>

        </tr>
        """

    html += "</table></body></html>"

    conn.close()

    return html


# ======================
# ACTIVATE
# ======================

@app.route("/activate")
@requires_auth
def activate():

    device = request.args.get("device")

    conn = db()
    c = conn.cursor()

    c.execute(
        "UPDATE devices SET is_active=1 WHERE device_id=?",
        (device,)
    )

    conn.commit()
    conn.close()

    return "Device Activated"


# ======================
# BLOCK
# ======================

@app.route("/block")
@requires_auth
def block():

    device = request.args.get("device")

    conn = db()
    c = conn.cursor()

    c.execute(
        "UPDATE devices SET is_blocked=1 WHERE device_id=?",
        (device,)
    )

    conn.commit()
    conn.close()

    return "Device Blocked"


# ======================
# EXTEND
# ======================

@app.route("/extend")
@requires_auth
def extend():

    device = request.args.get("device")

    days = int(request.args.get("days", 30))

    conn = db()
    c = conn.cursor()

    expire = datetime.datetime.utcnow() + datetime.timedelta(days=days)

    c.execute(
        "UPDATE devices SET expires_at=? WHERE device_id=?",
        (expire.isoformat(), device)
    )

    conn.commit()
    conn.close()

    return f"Extended {days} days"


# ======================

init_db()
