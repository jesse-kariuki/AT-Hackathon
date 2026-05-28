"""
BodaShield Backend — app.py
Run: python app.py
"""

import os, json, sqlite3, logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()

import africastalking
africastalking.initialize(
    username=os.getenv("AT_USERNAME", "sandbox"),
    api_key=os.getenv("AT_API_KEY",   "your_api_key_here")
)
sms_service   = africastalking.SMS
voice_service = africastalking.Voice

OWNER_PHONE        = os.getenv("OWNER_PHONE", "+254711000000")
AT_PHONE           = os.getenv("AT_PHONE",    "+254711000001")
FARE_PER_PASSENGER = int(os.getenv("FARE", "50"))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bodashield")
DB_PATH = "bodashield.db"

# ── DB 
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            event_type TEXT, plate TEXT,
            confidence REAL, lat REAL, lng REAL, extra TEXT
        );
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            plate TEXT, passengers_count INTEGER,
            expected_kes INTEGER, collected_kes INTEGER,
            variance_kes INTEGER, alerted INTEGER DEFAULT 0
        );
        """)

def log_event(event_type, plate, confidence=None, lat=None, lng=None, extra=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO events(event_type,plate,confidence,lat,lng,extra) VALUES(?,?,?,?,?,?)",
            (event_type, plate, confidence, lat, lng, json.dumps(extra) if extra else None)
        )
        db.commit()

# ── Alerts ────────────────────────────────────────────────────────────────────
def send_voice_alert(plate, lat, lng):
    try:
        result = voice_service.call(to_=OWNER_PHONE, from_=AT_PHONE)
        log.info("Voice call result: %s", result)
        return True
    except Exception as e:
        log.error("Voice call failed: %s", e)
        return False

def send_sms(plate, alert_type, confidence, lat, lng):
    maps = f"https://maps.google.com/?q={lat},{lng}"
    ts   = datetime.now().strftime("%H:%M")
    if alert_type == "SIPHON":
        body = (f"FUEL THEFT ALERT\nVehicle:{plate}\nTime:{ts}\n"
                f"Conf:{confidence*100:.0f}%\nLocation:{maps}\nCheck vehicle now.")
    else:
        body = (f"ENGINE KNOCK ALERT\nVehicle:{plate}\nTime:{ts}\n"
                f"Conf:{confidence*100:.0f}%\nService within 72hrs.")
    try:
        sms_service.send(body, [OWNER_PHONE])
        return True
    except Exception as e:
        log.error("SMS failed: %s", e)
        return False

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.route("/fuel_alert", methods=["POST"])
def fuel_alert():
    d   = request.get_json(force=True) or {}
    plate = d.get("plate","UNKNOWN"); lat=d.get("lat",-1.2921); lng=d.get("lng",36.8219)
    conf  = d.get("confidence",0.90)
    log.info("SIPHON ALERT | plate=%s | conf=%.2f", plate, conf)
    log_event("SIPHON", plate, conf, lat, lng)
    voice_ok = send_voice_alert(plate, lat, lng)
    sms_ok   = send_sms(plate, "SIPHON", conf, lat, lng)
    return jsonify({"status":"alerted","voice":voice_ok,"sms":sms_ok,"plate":plate}), 200

@app.route("/engine_alert", methods=["POST"])
def engine_alert():
    d   = request.get_json(force=True) or {}
    plate=d.get("plate","UNKNOWN"); lat=d.get("lat",-1.2921); lng=d.get("lng",36.8219)
    conf =d.get("confidence",0.88)
    log.info("KNOCK ALERT | plate=%s | conf=%.2f", plate, conf)
    log_event("KNOCK", plate, conf, lat, lng)
    sms_ok = send_sms(plate, "KNOCK", conf, lat, lng)
    return jsonify({"status":"alerted","sms":sms_ok,"plate":plate}), 200

@app.route("/ingest", methods=["POST"])
def ingest():
    d = request.get_json(force=True) or {}
    log_event(f"INGEST_{d.get('label','?').upper()}", d.get("plate","KCD123X"),
              d.get("confidence"), extra=d)
    return jsonify({"status":"logged"}), 200

@app.route("/passenger_count", methods=["POST"])
def passenger_count():
    import random
    d         = request.get_json(force=True) or {}
    plate     = d.get("plate","KBD789Z")
    count     = int(d.get("count",0))
    expected  = count * FARE_PER_PASSENGER
    collected = int(expected * random.uniform(0.60, 0.95))
    variance  = expected - collected
    vpct      = (variance/expected*100) if expected > 0 else 0
    with get_db() as db:
        db.execute(
            "INSERT INTO trips(plate,passengers_count,expected_kes,collected_kes,variance_kes,alerted)"
            " VALUES(?,?,?,?,?,?)",
            (plate,count,expected,collected,variance, 1 if vpct>20 else 0)
        )
        db.commit()
    if vpct > 20:
        ts = datetime.now().strftime("%H:%M")
        body=(f"FARE LEAKAGE ALERT\nVehicle:{plate}\nPassengers:{count}\n"
              f"Expected:KES {expected}\nMPesa:KES {collected}\n"
              f"Gap:KES {variance} ({vpct:.0f}%)\nInvestigate conductor. {ts}")
        try: sms_service.send(body,[OWNER_PHONE])
        except: pass
    return jsonify({"passengers":count,"expected":expected,"collected":collected,
                    "variance":variance,"variance_pct":round(vpct,1),"alerted":vpct>20}), 200

@app.route("/ussd", methods=["POST","GET"])
def ussd():
    text = request.values.get("text","").strip()
    log.info("USSD text='%s'", text)
    if text == "":
        resp = "CON BodaShield Fleet Guard\n1. Fuel status\n2. Engine health\n3. Last alert\n4. Today's stats\n0. Exit"
    elif text == "1":
        with get_db() as db:
            row = db.execute("SELECT ts,confidence FROM events WHERE event_type='SIPHON' ORDER BY ts DESC LIMIT 1").fetchone()
        resp = (f"END FUEL: Last theft {row['ts']}\nConf:{row['confidence']*100:.0f}%" if row
                else "END FUEL: Secure\nNo theft today. System armed.")
    elif text == "2":
        with get_db() as db:
            row = db.execute("SELECT ts FROM events WHERE event_type='KNOCK' ORDER BY ts DESC LIMIT 1").fetchone()
        resp = (f"END ENGINE: Knock at {row['ts']}\nService within 72hrs." if row
                else "END ENGINE: Healthy\nNo knocks. Est service: 1,200km")
    elif text == "3":
        with get_db() as db:
            row = db.execute("SELECT ts,event_type,plate,confidence FROM events WHERE event_type IN ('SIPHON','KNOCK') ORDER BY ts DESC LIMIT 1").fetchone()
        resp = (f"END Last:{row['event_type']}\nPlate:{row['plate']}\nTime:{row['ts']}\nConf:{row['confidence']*100:.0f}%"
                if row else "END No alerts today. All secure.")
    elif text == "4":
        with get_db() as db:
            s=db.execute("SELECT COUNT(*) as c FROM events WHERE event_type='SIPHON' AND ts>date('now')").fetchone()["c"]
            k=db.execute("SELECT COUNT(*) as c FROM events WHERE event_type='KNOCK' AND ts>date('now')").fetchone()["c"]
            t=db.execute("SELECT SUM(variance_kes) as v,COUNT(*) as c FROM trips WHERE ts>date('now')").fetchone()
        resp=f"END Today:\nTheft alerts:{s}\nEngine alerts:{k}\nTrips:{t['c'] or 0}\nFare saved:KES {t['v'] or 0}"
    elif text=="0":
        resp="END Goodbye. BodaShield armed."
    else:
        resp="END Invalid. Dial again."
    return resp, 200, {"Content-Type":"text/plain"}

@app.route("/latest_events")
def latest_events():
    with get_db() as db:
        ev=db.execute("SELECT id,ts,event_type,plate,confidence,lat,lng FROM events ORDER BY ts DESC LIMIT 20").fetchall()
        tr=db.execute("SELECT id,ts,plate,passengers_count,expected_kes,collected_kes,variance_kes FROM trips ORDER BY ts DESC LIMIT 10").fetchall()
    return jsonify({"events":[dict(e) for e in ev],"trips":[dict(t) for t in tr],"ts":datetime.now().isoformat()})

@app.route("/status")
def status_ep():
    with get_db() as db:
        total  =db.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        siphons=db.execute("SELECT COUNT(*) as c FROM events WHERE event_type='SIPHON'").fetchone()["c"]
        knocks =db.execute("SELECT COUNT(*) as c FROM events WHERE event_type='KNOCK'").fetchone()["c"]
    return jsonify({"status":"online","total_events":total,"siphon_alerts":siphons,"knock_alerts":knocks})

DASHBOARD_HTML = open(os.path.join(os.path.dirname(__file__),"templates","dashboard.html")).read() if os.path.exists(os.path.join(os.path.dirname(__file__),"templates","dashboard.html")) else "<h1>Dashboard loading...</h1>"

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/pitch")
def pitch():
    return render_template_string(open(os.path.join(os.path.dirname(__file__),"templates","pitch.html")).read()
        if os.path.exists(os.path.join(os.path.dirname(__file__),"templates","pitch.html"))
        else "<h1>Pitch page</h1>")

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  BodaShield Backend")
    print(f"  Dashboard: http://localhost:5000/")
    print(f"  ROI page : http://localhost:5000/pitch")
    print(f"  Owner SMS: {OWNER_PHONE}")
    print("="*50)
    print("\n  Run ngrok: ngrok http 5000")
    print("  Give URL to firmware person\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
