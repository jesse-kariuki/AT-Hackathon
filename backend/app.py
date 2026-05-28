"""
BodaShield Backend — app.py
Run: python app.py
"""
import os, sqlite3, logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Africa's Talking SDK Setup ────────────────────────────────────────────────
import africastalking

# The SDK automatically switches between Live and Sandbox based on your .env username
import africastalking
import os

# It is best practice to let os.getenv pull these from your .env file!
africastalking.initialize(
    username=os.getenv("AT_USERNAME", "chemweno"),
    api_key=os.getenv("AT_API_KEY", "your_api_key_goes_in_the_env_file")
)

# Initialize the SMS service
sms = africastalking.SMS

OWNER_PHONE = os.getenv("OWNER_PHONE", "+254797237577")
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

# ── API Endpoints ─────────────────────────────────────────────────────────────

# 1. The custom route you requested for testing
@app.route('/send-sms', methods=['POST'])
def custom_send_sms():
    data = request.get_json(force=True) or {}
    phone_number = data.get("phoneNumber")

    if not phone_number:
        return jsonify({"message": "Phone number not found"}), 400

    # SAFETY CATCH
    phone_number = "+" + str(phone_number).strip("+")

    # 1. Create the custom formatted message!
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M")
    
    custom_body = (f"BodaShield Alert\n"
                   f"Siphoning detected!\n"
                   f"Plate: KCD 123X (TEST)\n"
                   f"Time: {ts}\n"
                   f"Action: Dispatch security.")

    try:
        response = sms.send(
            # 2. Replace the old "Hello" string with our new variable
            message=custom_body, 
            recipients=[phone_number],
            sender_id="AFTKNG"
        )  

        return jsonify({"status": "success", "data": response}), 200
    except Exception as e:
        return jsonify({"message": "An error occurred while sending SMS", "error": str(e)}), 500
# 2. The Hardware Route (Updated to use the official SDK)
@app.route("/fuel_alert", methods=["POST"])
def fuel_alert():
    d = request.get_json(force=True) or {}
    plate = d.get("plate", "UNKNOWN")
    conf = d.get("confidence", 0.90)
    
    log.info("SIPHON ALERT | plate=%s | conf=%.2f", plate, conf)
    log_event("SIPHON", plate, conf)
    
    ts = datetime.now().strftime("%H:%M")
    body = (f"🚨 FUEL THEFT ALERT 🚨\n"
            f"Vehicle: {plate}\n"
            f"Time: {ts}\n"
            f"Conf: {conf*100:.0f}%\n"
            f"Check vehicle now.")
            
    try:
        # Using the exact same SDK format as your custom route
        response = sms.send(
            message=body,
            recipients=[OWNER_PHONE],
            sender_id="AFTKNG"
        )
        log.info("SDK Response: %s", response)
        sms_ok = True
    except Exception as e:
        log.error("SMS failed: %s", e)
        sms_ok = False
    
    return jsonify({"status": "alerted", "sms": sms_ok, "plate": plate}), 200


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


@app.route("/ussd", methods=["POST", "GET"])
def ussd():
    text = request.values.get("text", "").strip()
    
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
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

    init_db()
    
    print("\n" + "="*50)
    print("  BodaShield Backend - OFFICIAL SDK EDITION")
    print(f"  Logistics API: http://localhost:5000/api/fleet_status")
    print(f"  Owner SMS: {OWNER_PHONE}")
    print("="*50)
    
    app.run(host="0.0.0.0", port=5000, debug=True)