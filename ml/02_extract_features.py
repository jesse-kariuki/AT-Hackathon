import os, sqlite3, logging
import requests
import urllib3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# Suppress the Wi-Fi bypass warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

OWNER_PHONE = os.getenv("OWNER_PHONE", "+254700000000")

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bodashield")
DB_PATH = "bodashield.db"

# ── Database Setup ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now', 'localtime')),
            event_type TEXT, 
            plate TEXT,
            confidence REAL
        );
        """)

def log_event(event_type, plate, confidence=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO events(event_type, plate, confidence) VALUES(?, ?, ?)",
            (event_type, plate, confidence)
        )
        db.commit()

# ── The Sandbox SMS Bypass ────────────────────────────────────────────────────
def send_sms(dynamic_message):
    # Hardcoded back to Sandbox!
    url = "https://api.sandbox.africastalking.com/version1/messaging"
    
    headers = {
        "Accept": "application/json",
        "apiKey": os.getenv("AT_API_KEY", "your_sandbox_api_key")
    }
    
    data = {
        "username": "sandbox", # Force sandbox username
        "to": OWNER_PHONE,
        "message": dynamic_message
        # Notice: No Sender ID ("from") needed for Sandbox!
    }
    
    try:
        # verify=False punches through the hackathon Wi-Fi
        response = requests.post(url, headers=headers, data=data, verify=False)
        log.info("Sandbox SMS Response: %s", response.text)
        return True
    except Exception as e:
        log.error("SMS failed: %s", e)
        return False

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/fuel_alert", methods=["POST"])
def fuel_alert():
    d = request.get_json(force=True) or {}
    
    # 1. Get the raw ML data
    plate = d.get("plate", "UNKNOWN")
    conf = d.get("confidence", 0.0)
    
    # 2. Get the DYNAMIC message from the ML team!
    # (If they forget to send one, it uses the fallback message on the right)
    ml_message = d.get("message", f"🚨 Default Alert: Activity on {plate}.")
    
    log.info("SIPHON ALERT | plate=%s | conf=%.2f", plate, conf)
    log_event("SIPHON", plate, conf)
    
    # 3. Send whatever the ML team wrote directly to the phone
    sms_ok = send_sms(ml_message)
    
    return jsonify({"status": "alerted", "sms": sms_ok, "plate": plate, "sent_message": ml_message}), 200

@app.route("/api/fleet_status", methods=["GET"])
def fleet_status():
    with get_db() as db:
        events = db.execute(
            "SELECT ts, plate, confidence FROM events WHERE event_type='SIPHON' ORDER BY ts DESC LIMIT 10"
        ).fetchall()
        
        today_thefts = db.execute(
            "SELECT COUNT(*) as count FROM events WHERE event_type='SIPHON' AND ts > date('now')"
        ).fetchone()["count"]

    return jsonify({
        "status": "active",
        "today_siphon_alerts": today_thefts,
        "recent_alerts": [dict(e) for e in events]
    }), 200

@app.route("/")
def dashboard():
    return render_template("index.html")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

    init_db()
    
    print("\n" + "="*50)
    print("  BodaShield Backend - DYNAMIC ML SANDBOX EDITION")
    print(f"  Logistics API: http://localhost:5000/api/fleet_status")
    print(f"  Alert Phone: {OWNER_PHONE}")
    print("="*50)
    
    app.run(host="0.0.0.0", port=5000, debug=True)