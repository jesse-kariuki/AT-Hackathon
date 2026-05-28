"""
BodaShield Backend — app.py
Run: python app.py
"""
import os, sqlite3, logging, json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Africa's Talking Setup ────────────────────────────────────────────────────
import africastalking

africastalking.initialize(
    username=os.getenv("AT_USERNAME", "sandbox"),
    api_key=os.getenv("AT_API_KEY", "your_api_key_here")
)
sms_service = africastalking.SMS

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
        # Rebuilt to only track plate and confidence
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

# ── SMS Alert ─────────────────────────────────────────────────────────────────
def send_sms(plate, confidence):
    ts = datetime.now().strftime("%H:%M")
    
    body = (f"🚨 FUEL THEFT ALERT 🚨\n"
            f"Vehicle: {plate}\n"
            f"Time: {ts}\n"
            f"Conf: {confidence*100:.0f}%\n"
            f"Check vehicle now.")
    try:
        result = sms_service.send(body, [OWNER_PHONE])
        log.info("SMS Sent successfully: %s", result)
        return True
    except Exception as e:
        log.error("SMS failed: %s", e)
        return False

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/fuel_alert", methods=["POST"])
def fuel_alert():
    """Endpoint for the ESP32 to hit when siphoning sound is detected."""
    d = request.get_json(force=True) or {}
    plate = d.get("plate", "UNKNOWN")
    conf = d.get("confidence", 0.90)
    
    log.info("SIPHON ALERT | plate=%s | conf=%.2f", plate, conf)
    
    # 1. Log to database
    log_event("SIPHON", plate, conf)
    
    # 2. Trigger Africa's Talking SMS
    sms_ok = send_sms(plate, conf)
    
    return jsonify({"status": "alerted", "sms": sms_ok, "plate": plate}), 200


@app.route("/api/fleet_status", methods=["GET"])
def fleet_status():
    """API for the Logistics Company Dashboard to pull active theft alerts."""
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


@app.route("/ussd", methods=["POST", "GET"])
def ussd():
    """Offline USSD Menu for the Fleet Owner."""
    text = request.values.get("text", "").strip()
    log.info("USSD text='%s'", text)
    
    if text == "":
        resp = "CON BodaShield Fleet Guard\n1. Check Fuel Security\n2. Today's Stats\n0. Exit"
    elif text == "1":
        with get_db() as db:
            row = db.execute("SELECT ts, confidence FROM events WHERE event_type='SIPHON' ORDER BY ts DESC LIMIT 1").fetchone()
        resp = (f"END FUEL: Last theft {row['ts']}\nConf:{row['confidence']*100:.0f}%" if row 
                else "END FUEL: Secure\nNo theft today. System armed.")
    elif text == "2":
        with get_db() as db:
            s = db.execute("SELECT COUNT(*) as c FROM events WHERE event_type='SIPHON' AND ts>date('now')").fetchone()["c"]
        resp = f"END Today:\nTheft alerts: {s}\nAll vehicles tracked."
    elif text == "0":
        resp = "END Goodbye. BodaShield armed."
    else:
        resp = "END Invalid. Dial again."
        
    return resp, 200, {"Content-Type": "text/plain"}


@app.route("/")
def dashboard():
    return render_template_string("<h1>BodaShield Logistics API Online</h1><p>Query /api/fleet_status for data.</p>")


if __name__ == "__main__":
    # Ensures a clean database slate when you restart
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

    init_db()
    
    print("\n" + "="*50)
    print("  BodaShield Backend - SMS ONLY Edition")
    print(f"  Logistics API: http://localhost:5000/api/fleet_status")
    print(f"  Owner SMS: {OWNER_PHONE}")
    print("="*50)
    print("\n  Run ngrok: ngrok http 5000")
    print("  Give ngrok URL to ESP32 firmware dev\n")
    
    app.run(host="0.0.0.0", port=5000, debug=True)