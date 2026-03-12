
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sqlite3
import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging

# ==========================================
# 1. إعدادات السيرفر وقاعدة البيانات (Flask)
# ==========================================
app = Flask(__name__)
CORS(app)

# إخفاء رسائل السيرفر المزعجة من الكونسول
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

DB_FILE = 'eagle_drm.db'


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

    # ترقية القاعدة القديمة بدون فقدان البيانات
    if not column_exists(c, 'devices', 'expires_at'):
        c.execute("ALTER TABLE devices ADD COLUMN expires_at TEXT")

    conn.commit()
    conn.close()


def get_real_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    real_ip = request.headers.get('X-Real-IP', '')
    cf_ip = request.headers.get('CF-Connecting-IP', '')

    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    if real_ip:
        return real_ip.strip()
    if cf_ip:
        return cf_ip.strip()
    return request.remote_addr or 'Unknown'


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


@app.route('/api', methods=['GET'])
def heartbeat():
    device_id = request.args.get('device')
    server_name = request.args.get('server', 'غير محدد')
    now_playing = request.args.get('playing', 'يتصفح القوائم...')
    device_model = request.args.get('model', 'غير معروف')

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
            if ip_address not in ['127.0.0.1', '::1', 'Unknown']:
                res = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=2).json()
                country = res.get('country', 'Unknown')
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


def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


# ==========================================
# 2. واجهة البرنامج (Desktop GUI)
# ==========================================
class EagleAdminApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🦅 THE EAGLE IPTV - برنامج إدارة الاشتراكات 🦅")
        self.root.geometry("1220x640")
        self.root.configure(bg="#111111")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#222222",
            foreground="#ffffff",
            fieldbackground="#222222",
            rowheight=30,
            font=('Arial', 10)
        )
        style.map('Treeview', background=[('selected', '#d4af37')], foreground=[('selected', '#000000')])
        style.configure("Treeview.Heading", background="#d4af37", foreground="#000000", font=('Arial', 11, 'bold'))

        title_label = tk.Label(
            root,
            text="🦅 لوحة تحكم وتفعيل الأجهزة - THE EAGLE 🦅",
            font=("Arial", 18, "bold"),
            bg="#111111",
            fg="#d4af37",
            pady=15
        )
        title_label.pack()

        btn_frame = tk.Frame(root, bg="#111111")
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="✅ تفعيل الجهاز", bg="#00ff88", fg="#000", font=("Arial", 11, "bold"),
                  width=15, command=lambda: self.update_status("activate")).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="⏳ إلغاء التفعيل", bg="#ffa500", fg="#000", font=("Arial", 11, "bold"),
                  width=15, command=lambda: self.update_status("deactivate")).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="🚫 حظر نهائي", bg="#ff4b4b", fg="#fff", font=("Arial", 11, "bold"),
                  width=15, command=lambda: self.update_status("block")).grid(row=0, column=2, padx=5)
        tk.Button(btn_frame, text="♻️ فك الحظر", bg="#888888", fg="#fff", font=("Arial", 11, "bold"),
                  width=15, command=lambda: self.update_status("unblock")).grid(row=0, column=3, padx=5)
        tk.Button(btn_frame, text="📅 ضبط انتهاء", bg="#4da3ff", fg="#000", font=("Arial", 11, "bold"),
                  width=15, command=self.set_expiry).grid(row=0, column=4, padx=5)
        tk.Button(btn_frame, text="🧹 إزالة الانتهاء", bg="#9b59b6", fg="#fff", font=("Arial", 11, "bold"),
                  width=15, command=self.clear_expiry).grid(row=0, column=5, padx=5)

        columns = ("device_id", "model", "ip", "country", "server", "playing", "expires_at", "last_seen", "status")
        self.tree = ttk.Treeview(root, columns=columns, show="headings")

        self.tree.heading("device_id", text="رقم الجهاز")
        self.tree.heading("model", text="نوع الجهاز")
        self.tree.heading("ip", text="الآي بي")
        self.tree.heading("country", text="الدولة")
        self.tree.heading("server", text="السيرفر الحالي")
        self.tree.heading("playing", text="يشاهد الآن")
        self.tree.heading("expires_at", text="انتهاء الاشتراك")
        self.tree.heading("last_seen", text="آخر ظهور")
        self.tree.heading("status", text="حالة الاشتراك")

        self.tree.column("device_id", width=190, anchor="center")
        self.tree.column("model", width=120, anchor="center")
        self.tree.column("ip", width=100, anchor="center")
        self.tree.column("country", width=90, anchor="center")
        self.tree.column("server", width=100, anchor="center")
        self.tree.column("playing", width=180, anchor="center")
        self.tree.column("expires_at", width=130, anchor="center")
        self.tree.column("last_seen", width=140, anchor="center")
        self.tree.column("status", width=130, anchor="center")

        self.tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.status_lbl = tk.Label(root, text="جاري تشغيل السيرفر...", bg="#111", fg="#00ff88", font=("Arial", 10))
        self.status_lbl.pack(side=tk.BOTTOM, pady=5)

        self.refresh_data()

    def get_selected_device_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("تنبيه", "يرجى اختيار جهاز من الجدول أولاً!")
            return None
        return self.tree.item(selected[0])['values'][0]

    def refresh_data(self):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        devices = c.fetchall()
        conn.close()

        for row in self.tree.get_children():
            self.tree.delete(row)

        for d in devices:
            device_id = d[0]
            ip = d[1]
            country = d[2]
            server = d[3]
            playing = d[4]
            model = d[5]
            last_seen = d[6]
            is_active = d[7]
            is_blocked = d[8]
            expires_at = d[9] if len(d) > 9 else None

            if is_blocked:
                status_text = "محظور 🚫"
            elif is_expired(expires_at):
                status_text = "منتهي ⌛"
            elif is_active:
                status_text = "مفعل ✅"
            else:
                status_text = "بانتظار التفعيل ⏳"

            self.tree.insert(
                "",
                tk.END,
                values=(
                    device_id,
                    model,
                    ip,
                    country,
                    server,
                    playing,
                    expires_at or "غير محدد",
                    last_seen,
                    status_text
                )
            )

        self.root.after(3000, self.refresh_data)

    def update_status(self, action):
        device_id = self.get_selected_device_id()
        if not device_id:
            return

        conn = get_db_connection()
        c = conn.cursor()

        if action == "activate":
            c.execute("UPDATE devices SET is_active = 1, is_blocked = 0 WHERE device_id=?", (device_id,))
            self.status_lbl.config(text=f"تم تفعيل الجهاز: {device_id}", fg="#00ff88")
        elif action == "deactivate":
            c.execute("UPDATE devices SET is_active = 0 WHERE device_id=?", (device_id,))
            self.status_lbl.config(text=f"تم إلغاء تفعيل: {device_id}", fg="#ffa500")
        elif action == "block":
            c.execute("UPDATE devices SET is_blocked = 1, is_active = 0 WHERE device_id=?", (device_id,))
            self.status_lbl.config(text=f"تم حظر الجهاز: {device_id}", fg="#ff4b4b")
        elif action == "unblock":
            c.execute("UPDATE devices SET is_blocked = 0 WHERE device_id=?", (device_id,))
            self.status_lbl.config(text=f"تم فك حظر: {device_id}", fg="#888888")

        conn.commit()
        conn.close()
        self.refresh_data()

    def set_expiry(self):
        device_id = self.get_selected_device_id()
        if not device_id:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("ضبط انتهاء الاشتراك")
        dialog.geometry("320x160")
        dialog.configure(bg="#111111")
        dialog.grab_set()

        tk.Label(dialog, text="عدد الأيام من اليوم:", bg="#111111", fg="#ffffff", font=("Arial", 11, "bold")).pack(pady=10)
        days_var = tk.StringVar(value="30")
        entry = tk.Entry(dialog, textvariable=days_var, justify="center", font=("Arial", 12))
        entry.pack(pady=5)

        def save_expiry():
            try:
                days = int(days_var.get().strip())
                expires_at = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("UPDATE devices SET expires_at=? WHERE device_id=?", (expires_at, device_id))
                conn.commit()
                conn.close()
                self.status_lbl.config(text=f"تم ضبط الانتهاء للجهاز: {device_id}", fg="#4da3ff")
                dialog.destroy()
                self.refresh_data()
            except:
                messagebox.showerror("خطأ", "يرجى إدخال رقم صحيح للأيام")

        tk.Button(dialog, text="حفظ", command=save_expiry, bg="#4da3ff", fg="#000", font=("Arial", 11, "bold")).pack(pady=15)

    def clear_expiry(self):
        device_id = self.get_selected_device_id()
        if not device_id:
            return

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE devices SET expires_at=NULL WHERE device_id=?", (device_id,))
        conn.commit()
        conn.close()
        self.status_lbl.config(text=f"تم إزالة الانتهاء للجهاز: {device_id}", fg="#9b59b6")
        self.refresh_data()


# ==========================================
# 3. تشغيل المنظومة
# ==========================================
if __name__ == '__main__':
    init_db()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    root = tk.Tk()
    app = EagleAdminApp(root)
    root.mainloop()
