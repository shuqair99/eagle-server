import sqlite3
import datetime
import logging
import requests
from functools import wraps
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

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

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

DB_FILE = "/tmp/eagle_drm.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE,
        server TEXT,
        model TEXT,
        device_type TEXT,
        ip TEXT,
        country TEXT,
        flag TEXT,
        created_at TEXT,
        last_seen TEXT,
        is_active INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        expires_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def expired(date):
    if not date:
        return False
    return datetime.datetime.utcnow() > datetime.datetime.fromisoformat(date)

def get_device_type(user_agent):
    ua = user_agent.lower()
    if any(tv in ua for tv in ['smart-tv', 'tizen', 'webos', 'appletv']): return "Smart TV"
    if 'android' in ua: return "Android (Mobile/Box)"
    if any(ios in ua for ios in ['iphone', 'ipad']): return "iOS Device"
    if 'windows' in ua: return "Windows PC"
    if 'macintosh' in ua: return "Mac"
    return "Unknown Device"

def get_geo_info(ip):
    if not ip or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('127.'):
        return "Local Network", "🏠"
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=country,countryCode", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            country = data.get("country", "Unknown")
            cc = data.get("countryCode", "UN")
            flag = "".join(chr(ord(c) + 127397) for c in cc) if cc != "UN" else "🏳️"
            return country, flag
    except Exception:
        pass
    return "Unknown", "🏳️"

@app.route("/banner.png")
def banner():
    return send_from_directory(BASE_DIR, "banner.png")

@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "eagle-server"})

@app.route("/api")
def api():
    device = request.args.get("device")
    server = request.args.get("server")
    model = request.args.get("model")
    
    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ip = raw_ip.split(',')[0].strip() if raw_ip else ""

    user_agent = request.headers.get("User-Agent", "")
    device_type = get_device_type(user_agent)

    if not device:
        return jsonify({"error": "device missing"})

    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT is_active, is_blocked, expires_at FROM devices WHERE device_id=?",
        (device,)
    )
    row = c.fetchone()
    now = datetime.datetime.utcnow().isoformat()

    if not row:
        country, flag = get_geo_info(ip)
        
        c.execute("""
        INSERT INTO devices(device_id, server, model, device_type, ip, country, flag, created_at, last_seen)
        VALUES(?,?,?,?,?,?,?,?,?)
        """, (device, server, model, device_type, ip, country, flag, now, now))
        conn.commit()
        conn.close()
        return jsonify({"status": "pending"})

    is_active, is_blocked, exp = row
    country, flag = get_geo_info(ip)
    
    c.execute(
        "UPDATE devices SET last_seen=?, server=?, model=?, device_type=?, ip=?, country=?, flag=? WHERE device_id=?",
        (now, server, model, device_type, ip, country, flag, device)
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

@app.route("/admin")
@requires_auth
def admin():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM devices ORDER BY id DESC")
    rows = c.fetchall()

    total_devices = len(rows)
    active_count = sum(1 for r in rows if r[10] == 1 and r[11] == 0 and not expired(r[12]))
    blocked_count = sum(1 for r in rows if r[11] == 1)
    pending_count = sum(1 for r in rows if r[10] == 0 and r[11] == 0)
    expired_count = sum(1 for r in rows if expired(r[12]))

    html = """
    <html>
    <head>
    <title>Eagle IPTV Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:linear-gradient(180deg,#020617 0%,#0f172a 100%);font-family:Arial,sans-serif;color:white;padding:25px;}
    .container{max-width:1700px;margin:auto;}
    .banner{width:100%;height:220px;object-fit:cover;border-radius:16px;margin-bottom:25px;box-shadow:0 0 30px rgba(255,215,0,0.18);border:1px solid rgba(255,215,0,0.18);}
    .title{font-size:36px;font-weight:800;color:#f8d35e;margin-bottom:10px;text-shadow:0 0 18px rgba(255,215,0,0.18);}
    .subtitle{color:#94a3b8;margin-bottom:25px;font-size:15px;}
    .topbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px;flex-wrap:wrap;}
    .search-box{flex:1;min-width:260px;}
    .search-box input{width:100%;background:#0f172a;border:1px solid rgba(255,215,0,0.12);color:white;border-radius:12px;padding:12px 14px;outline:none;font-size:14px;}
    .stats{display:grid;grid-template-columns:repeat(5,1fr);gap:15px;margin-bottom:25px;}
    .card{background:rgba(15,23,42,0.85);border:1px solid rgba(255,215,0,0.12);border-radius:14px;padding:18px;box-shadow:0 0 20px rgba(0,0,0,0.25);transition:0.25s ease;}
    .card:hover{transform:translateY(-2px);border-color:rgba(255,215,0,0.28);}
    .card h3{color:#94a3b8;font-size:14px;margin-bottom:10px;font-weight:600;}
    .card p{color:#f8d35e;font-size:28px;font-weight:800;}
    .table-wrap{overflow-x:auto;border-radius:16px;border:1px solid rgba(255,215,0,0.12);box-shadow:0 0 20px rgba(0,0,0,0.25);}
    table{border-collapse:collapse;width:100%;min-width:1450px;background:rgba(15,23,42,0.92);}
    th, td{padding:14px 12px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);}
    th{background:#16233a;color:#f8d35e;font-size:14px;position:sticky;top:0;}
    tr:hover{background:rgba(255,255,255,0.03);}
    .status{display:inline-block;min-width:95px;padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:0.4px;}
    .active{background:rgba(34,197,94,0.16);color:#4ade80;border:1px solid rgba(34,197,94,0.35);}
    .blocked{background:rgba(239,68,68,0.16);color:#f87171;border:1px solid rgba(239,68,68,0.35);}
    .pending{background:rgba(250,204,21,0.12);color:#facc15;border:1px solid rgba(250,204,21,0.35);}
    .expired{background:rgba(249,115,22,0.16);color:#fb923c;border:1px solid rgba(249,115,22,0.35);}
    .actions{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:8px;}
    .btn{display:inline-block;padding:8px 12px;border-radius:10px;text-decoration:none;font-size:12px;font-weight:700;transition:0.2s ease;border:1px solid transparent;}
    .btn:hover{transform:translateY(-1px);opacity:0.95;}
    .btn-activate{background:#16a34a;color:white;}
    .btn-block{background:#dc2626;color:white;}
    .btn-extend{background:#d4af37;color:#111827;}
    .btn-delete{background:#7f1d1d;color:white;}
    .muted{color:#94a3b8;font-size:13px;}
    .flag{font-size:18px; margin-right:5px;}
    @media (max-width: 1200px){.stats{grid-template-columns:repeat(3,1fr);}}
    @media (max-width: 900px){.stats{grid-template-columns:repeat(2,1fr);} .banner{height:150px;} .title{font-size:28px;}}
    @media (max-width: 540px){.stats{grid-template-columns:1fr;} body{padding:14px;} .banner{height:110px;}}
    </style>
    <script>
    function filterDevices() {
        const input = document.getElementById("deviceSearch").value.toLowerCase();
        const rows = document.querySelectorAll("tbody tr");
        rows.forEach(row => {
            row.style.display = row.innerText.toLowerCase().includes(input) ? "" : "none";
        });
    }
    </script>
    </head>
    <body>
    <div class="container">
    <img src="/banner.png" class="banner" alt="Eagle IPTV Panel Banner">
    <div class="topbar">
        <div>
            <div class="title">Eagle IPTV Panel</div>
            <div class="subtitle">Secure Device Management Dashboard</div>
        </div>
        <div class="search-box">
            <input id="deviceSearch" onkeyup="filterDevices()" type="text" placeholder="Search by device, server, model, IP or country...">
        </div>
    </div>

    <div class="stats">
        <div class="card"><h3>Total Devices</h3><p>__TOTAL__</p></div>
        <div class="card"><h3>Active Devices</h3><p>__ACTIVE__</p></div>
        <div class="card"><h3>Pending Devices</h3><p>__PENDING__</p></div>
        <div class="card"><h3>Blocked Devices</h3><p>__BLOCKED__</p></div>
        <div class="card"><h3>Expired Devices</h3><p>__EXPIRED__</p></div>
    </div>

    <div class="table-wrap">
    <table>
    <thead>
    <tr>
        <th>ID</th>
        <th>Device</th>
        <th>Type & Details</th>
        <th>Location</th>
        <th>IP Address</th>
        <th>Status</th>
        <th>Expire</th>
        <th>Created</th>
        <th>Actions</th>
    </tr>
    </thead>
    <tbody>
    """

    html = html.replace("__TOTAL__", str(total_devices))
    html = html.replace("__ACTIVE__", str(active_count))
    html = html.replace("__PENDING__", str(pending_count))
    html = html.replace("__BLOCKED__", str(blocked_count))
    html = html.replace("__EXPIRED__", str(expired_count))

    for r in rows:
        (
            row_id,
            device,
            server,
            model,
            device_type,
            ip,
            country,
            flag,
            created,
            last,
            active,
            blocked,
            exp
        ) = r

        if blocked:
            status_label = "BLOCKED"
            status_class = "blocked"
        elif expired(exp):
            status_label = "EXPIRED"
            status_class = "expired"
        elif active:
            status_label = "ACTIVE"
            status_class = "active"
        else:
            status_label = "PENDING"
            status_class = "pending"

        type_model_display = f"<b>{device_type or 'Unknown'}</b><br><span class='muted'>{model or '-'}</span>"
        location_display = f"<span class='flag'>{flag or '🏳️'}</span> {country or 'Unknown'}"
        created_short = created.split('.')[0].replace('T', ' ') if created else "-"

        html += f"""
        <tr>
            <td>{row_id}</td>
            <td>{device}</td>
            <td>{type_model_display}</td>
            <td>{location_display}</td>
            <td><b>{ip or "-"}</b></td>
            <td><span class="status {status_class}">{status_label}</span></td>
            <td>{exp.split('T')[0] if exp else "-"}</td>
            <td class="muted">{created_short}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-activate" href="/activate?device={device}">Activate</a>
                    <a class="btn btn-block" href="/block?device={device}">Block</a>
                    <a class="btn btn-extend" href="/extend?device={device}&days=30">+30d</a>
                    <a class="btn btn-delete" href="/delete?device={device}">Delete</a>
                </div>
            </td>
        </tr>
        """

    html += """
    </tbody>
    </table>
    </div>
    </div>
    </body>
    </html>
    """

    conn.close()
    return html

@app.route("/activate")
@requires_auth
def activate():
    device = request.args.get("device")
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE devices SET is_active=1, is_blocked=0 WHERE device_id=?", (device,))
    conn.commit()
    conn.close()
    return Response('<script>window.location.href="/admin";</script>', mimetype="text/html")

@app.route("/block")
@requires_auth
def block():
    device = request.args.get("device")
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE devices SET is_blocked=1, is_active=0 WHERE device_id=?", (device,))
    conn.commit()
    conn.close()
    return Response('<script>window.location.href="/admin";</script>', mimetype="text/html")

@app.route("/extend")
@requires_auth
def extend():
    device = request.args.get("device")
    days = int(request.args.get("days", 30))
    conn = db()
    c = conn.cursor()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    c.execute("UPDATE devices SET expires_at=? WHERE device_id=?", (expire.isoformat(), device))
    conn.commit()
    conn.close()
    return Response('<script>window.location.href="/admin";</script>', mimetype="text/html")

@app.route("/delete")
@requires_auth
def delete():
    device = request.args.get("device")
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM devices WHERE device_id=?", (device,))
    conn.commit()
    conn.close()
    return Response('<script>window.location.href="/admin";</script>', mimetype="text/html")

init_db()
