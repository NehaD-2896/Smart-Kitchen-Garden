"""
LoRa-Based Smart Kitchen Garden Monitoring & Automated Irrigation System
-------------------------------------------------------------------------
Flask backend + dashboard.

Receives sensor readings (soil moisture, TDS, temperature) posted over
WiFi/HTTP by each ESP32 node (or by the gateway that aggregates all
LoRa nodes), stores them in SQLite, drives the live web dashboard,
decides when to trigger irrigation, and sends email alerts on
abnormal TDS.

Run:
    pip install -r requirements.txt
    python app.py

The server listens on 0.0.0.0:5000 by default so a Wokwi-simulated
ESP32 (via a public tunnel such as ngrok) or a real ESP32 on the same
WiFi network can reach it.
"""

import os
import sqlite3
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from flask import Flask, jsonify, request, render_template, g

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "kitchen_garden.db")

# Default thresholds (can be changed live from the dashboard)
DEFAULT_MOISTURE_MIN = 30.0   # % — below this -> irrigate
DEFAULT_TDS_MAX = 700.0       # ppm — above this -> email alert
DEFAULT_TDS_MIN = 100.0       # ppm — below this -> email alert (nutrient too low)

NODE_IDS = ["node1", "node2", "node3", "node4"]

# Email (SMTP) settings — set these as environment variables, do NOT hardcode
# real credentials in this file.
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")          # sender email
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # app password
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", "")  # who gets the alert

# Minimum gap between two alert emails for the same node (avoid spamming)
ALERT_COOLDOWN_MINUTES = 10

app = Flask(__name__)

# In-memory cooldown tracker: {node_id: last_alert_datetime}
_last_alert_sent = {}


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
    for node_id in NODE_IDS:
        c.execute("""
            INSERT OR IGNORE INTO thresholds (node_id, moisture_min, tds_min, tds_max)
            VALUES (?, ?, ?, ?)
        """, (node_id, DEFAULT_MOISTURE_MIN, DEFAULT_TDS_MIN, DEFAULT_TDS_MAX))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Email alert
# --------------------------------------------------------------------------

def send_email_alert(node_id, tds_value, reason):
    """Send an email notifying abnormal TDS. Silently skips if SMTP is
    not configured, and respects a per-node cooldown to avoid spamming."""
    now = datetime.now()
    last_sent = _last_alert_sent.get(node_id)
    if last_sent and (now - last_sent) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
        return False

    if not SMTP_USER or not SMTP_PASSWORD or not ALERT_RECIPIENT:
        print(f"[ALERT-SKIPPED] Email not configured. {node_id}: {reason} (TDS={tds_value})")
        return False

    subject = f"[Kitchen Garden Alert] Abnormal TDS on {node_id}"
    body = (
        f"Node: {node_id}\n"
        f"TDS reading: {tds_value} ppm\n"
        f"Reason: {reason}\n"
        f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Please check the nutrient balance in this plant pod."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ALERT_RECIPIENT

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [ALERT_RECIPIENT], msg.as_string())
        _last_alert_sent[node_id] = now
        return True
    except Exception as exc:
        print(f"[ALERT-ERROR] Failed to send email for {node_id}: {exc}")
        return False


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
# --------------------------------------------------------------------------

@app.route("/api/data", methods=["POST"])
def ingest_data():
    """
    Expected JSON body from an ESP32 node (or the LoRa gateway forwarding
    a node's packet):
    {
        "node_id": "node1",
        "soil_moisture": 42.5,
        "tds": 550.0,
        "temperature": 27.3
    }

    Returns JSON telling the node whether to switch its irrigation
    relay ON or OFF:
    { "irrigate": true/false }
    """
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

    # TDS out-of-range -> email alert
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
# API: thresholds (read / update from the dashboard)
# --------------------------------------------------------------------------

@app.route("/api/thresholds", methods=["GET"])
def get_thresholds():
    db = get_db()
    rows = db.execute("SELECT * FROM thresholds").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/thresholds/<node_id>", methods=["POST"])
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
# API: data for the dashboard UI
# --------------------------------------------------------------------------

@app.route("/api/latest")
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
def history(node_id):
    if node_id not in NODE_IDS:
        return jsonify({"error": "unknown node_id"}), 400
    db = get_db()
    rows = db.execute(
        """SELECT * FROM readings WHERE node_id=?
           ORDER BY id DESC LIMIT 50""",
        (node_id,),
    ).fetchall()
    rows = list(reversed(rows))  # chronological order for charts
    return jsonify([dict(r) for r in rows])


@app.route("/api/alerts")
def alerts():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# --------------------------------------------------------------------------
# Dashboard page
# --------------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html", node_ids=NODE_IDS)


# --------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
