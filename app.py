"""
LoRa-Based Smart Kitchen Garden Monitoring & Automated Irrigation System
-------------------------------------------------------------------------
Flask backend + dashboard.

Adds (per "Next Review" notes):
  1. User login for the dashboard (session-based).
  3. Email alert simulation — every alert is logged as a full simulated
     email (From/To/Subject/Body) viewable in an in-dashboard Inbox,
     whether or not real SMTP is configured.

Run:
    pip install -r requirements.txt
    python app.py

Default login: admin / admin123   (change via env vars, see below)
"""

import os
import sqlite3
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps

from flask import (
    Flask, jsonify, request, render_template, g,
    session, redirect, url_for, flash
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "kitchen_garden.db")

DEFAULT_MOISTURE_MIN = 30.0
DEFAULT_TDS_MAX = 700.0
DEFAULT_TDS_MIN = 100.0

NODE_IDS = ["node1", "node2", "node3", "node4"]

# Real SMTP settings (optional — leave blank to run in simulation-only mode)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", "kitchen.garden.alerts@example.com")

ALERT_COOLDOWN_MINUTES = 10

# --- Login config ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deploying")

app = Flask(__name__)
app.secret_key = SECRET_KEY

_last_alert_sent = {}


# --------------------------------------------------------------------------
# Login helpers
# --------------------------------------------------------------------------

def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            soil_moisture REAL,
            tds REAL,
            temperature REAL,
            irrigated INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS thresholds (
            node_id TEXT PRIMARY KEY,
            moisture_min REAL NOT NULL,
            tds_min REAL NOT NULL,
            tds_max REAL NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    # --- Task 3: simulated email inbox ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS simulated_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            really_sent INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)
    for node_id in NODE_IDS:
        c.execute("""
            INSERT OR IGNORE INTO thresholds (node_id, moisture_min, tds_min, tds_max)
            VALUES (?, ?, ?, ?)
        """, (node_id, DEFAULT_MOISTURE_MIN, DEFAULT_TDS_MIN, DEFAULT_TDS_MAX))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Email alert (real + simulated)
# --------------------------------------------------------------------------

def log_simulated_email(node_id, sender, recipient, subject, body, really_sent):
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """INSERT INTO simulated_emails
           (node_id, sender, recipient, subject, body, really_sent, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (node_id, sender, recipient, subject, body, int(really_sent),
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    db.close()


def send_email_alert(node_id, tds_value, reason):
    """Builds the alert email and ALWAYS logs it to the simulated inbox
    (Task 3), regardless of whether real SMTP is configured. If SMTP
    credentials are present, it additionally attempts a real send."""
    now = datetime.now()
    last_sent = _last_alert_sent.get(node_id)
    if last_sent and (now - last_sent) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
        return False

    sender = SMTP_USER if SMTP_USER else "kitchen-garden-system@simulated.local"
    subject = f"[Kitchen Garden Alert] Abnormal TDS on {node_id}"
    body = (
        f"Node: {node_id}\n"
        f"TDS reading: {tds_value} ppm\n"
        f"Reason: {reason}\n"
        f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Please check the nutrient balance in this plant pod."
    )

    really_sent = False
    if SMTP_USER and SMTP_PASSWORD and ALERT_RECIPIENT:
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = ALERT_RECIPIENT
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, [ALERT_RECIPIENT], msg.as_string())
            really_sent = True
        except Exception as exc:
            print(f"[ALERT-ERROR] Real send failed for {node_id}: {exc}")

    # Always log to the simulated inbox, whether or not the real send worked
    log_simulated_email(node_id, sender, ALERT_RECIPIENT, subject, body, really_sent)

    _last_alert_sent[node_id] = now
    return True


def log_alert(node_id, message):
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO alerts (node_id, message, timestamp) VALUES (?, ?, ?)",
        (node_id, message, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# API: ingest sensor data from ESP32 node / gateway
# (left open, no login_required — hardware can't log in; see note below)
# --------------------------------------------------------------------------

@app.route("/api/data", methods=["POST"])
def ingest_data():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "invalid or missing JSON body"}), 400

    node_id = data.get("node_id")
    if node_id not in NODE_IDS:
        return jsonify({"error": f"unknown node_id '{node_id}'"}), 400

    try:
        soil_moisture = float(data["soil_moisture"])
        tds = float(data["tds"])
        temperature = float(data["temperature"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "soil_moisture, tds, temperature must be numeric"}), 400

    db = get_db()
    thresh = db.execute(
        "SELECT * FROM thresholds WHERE node_id = ?", (node_id,)
    ).fetchone()

    irrigate = soil_moisture < thresh["moisture_min"]

    db.execute(
        """INSERT INTO readings
           (node_id, soil_moisture, tds, temperature, irrigated, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (node_id, soil_moisture, tds, temperature, int(irrigate),
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()

    if tds > thresh["tds_max"]:
        reason = f"TDS above max threshold ({thresh['tds_max']} ppm)"
        if send_email_alert(node_id, tds, reason):
            log_alert(node_id, reason)
    elif tds < thresh["tds_min"]:
        reason = f"TDS below min threshold ({thresh['tds_min']} ppm)"
        if send_email_alert(node_id, tds, reason):
            log_alert(node_id, reason)

    return jsonify({"irrigate": irrigate})


# --------------------------------------------------------------------------
# API: thresholds (login required — dashboard only)
# --------------------------------------------------------------------------

@app.route("/api/thresholds", methods=["GET"])
@login_required
def get_thresholds():
    db = get_db()
    rows = db.execute("SELECT * FROM thresholds").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/thresholds/<node_id>", methods=["POST"])
@login_required
def update_thresholds(node_id):
    if node_id not in NODE_IDS:
        return jsonify({"error": "unknown node_id"}), 400

    data = request.get_json(force=True, silent=True) or request.form
    try:
        moisture_min = float(data["moisture_min"])
        tds_min = float(data["tds_min"])
        tds_max = float(data["tds_max"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "moisture_min, tds_min, tds_max are required numbers"}), 400

    db = get_db()
    db.execute(
        """UPDATE thresholds SET moisture_min=?, tds_min=?, tds_max=?
           WHERE node_id=?""",
        (moisture_min, tds_min, tds_max, node_id),
    )
    db.commit()
    return jsonify({"status": "updated"})


# --------------------------------------------------------------------------
# API: data for the dashboard UI (login required)
# --------------------------------------------------------------------------

@app.route("/api/latest")
@login_required
def latest_readings():
    db = get_db()
    result = {}
    for node_id in NODE_IDS:
        row = db.execute(
            """SELECT * FROM readings WHERE node_id=?
               ORDER BY id DESC LIMIT 1""",
            (node_id,),
        ).fetchone()
        result[node_id] = dict(row) if row else None
    return jsonify(result)


@app.route("/api/history/<node_id>")
@login_required
def history(node_id):
    if node_id not in NODE_IDS:
        return jsonify({"error": "unknown node_id"}), 400
    db = get_db()
    rows = db.execute(
        """SELECT * FROM readings WHERE node_id=?
           ORDER BY id DESC LIMIT 50""",
        (node_id,),
    ).fetchall()
    rows = list(reversed(rows))
    return jsonify([dict(r) for r in rows])


@app.route("/api/alerts")
@login_required
def alerts():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# --- Task 3: simulated inbox API ---
@app.route("/api/inbox")
@login_required
def inbox_api():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM simulated_emails ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", node_ids=NODE_IDS,
                            username=session.get("username"))


# --- Task 3: simulated inbox page ---
@app.route("/inbox")
@login_required
def inbox_page():
    return render_template("inbox.html", username=session.get("username"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
