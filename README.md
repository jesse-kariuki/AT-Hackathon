# BodaShield — Complete Setup Guide

> ESP32 + acoustic AI + Africa's Talking
> Detects fuel theft and engine faults. Calls you when it happens.

---

## BEFORE YOU START — One-time setup (do this before the hackathon)

### 1. Clone / create the project
```bash
git clone <your-repo> bodashield
cd bodashield
```

### 2. Python environment
```bash
python -m venv venv

# Mac/Linux:
source venv/bin/activate

# Windows:
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Africa's Talking account
1. Sign up at https://account.africastalking.com
2. Go to Settings → API Key → copy it
3. Go to Sandbox → Phone Numbers → add YOUR real phone number (so you receive alerts)
4. Copy `backend/.env.example` → `backend/.env`
5. Fill in AT_USERNAME, AT_API_KEY, OWNER_PHONE

### 4. Arduino IDE setup
1. Download Arduino IDE 2.x from https://arduino.cc
2. Open Preferences → Additional Board Manager URLs → add:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Tools → Board → Board Manager → search "esp32" → Install "esp32 by Espressif Systems"
4. Install libraries (Tools → Manage Libraries):
   - ArduinoJson by Benoit Blanchon
5. Plug in ESP32, go to Tools → Board → select "ESP32 Dev Module"
6. Tools → Port → select your COM port (Windows: COMx, Linux: /dev/ttyUSB0)

### 5. ngrok
```bash
# Install from https://ngrok.com/download
# Sign up for free account, copy auth token
ngrok config add-authtoken YOUR_TOKEN
```

---

## HACKATHON DAY — Exact sequence

### HOUR 0: Everyone do this together (15 min)

```bash
# Terminal 1 — Backend person
cd bodashield/backend
cp .env.example .env
# Edit .env with your AT credentials and phone number
python app.py
# Should print: "BodaShield Backend" and "http://localhost:5000/"

# Terminal 2 — Backend person (new terminal)
ngrok http 5000
# Copy the https://xxxxx.ngrok.io URL
# IMMEDIATELY give this URL to the firmware person
```

Test the backend is alive:
```bash
curl http://localhost:5000/status
# Should return: {"status":"online",...}
```

---

### HOURS 0–6: ML Person

#### Step 1 — Record audio (hours 0–2)
Open Terminal, navigate to `bodashield/ml/`

```bash
# Record Class 0: pump hum (run tap near your laptop mic)
python 01_collect_audio.py --class 0 --label pump_hum

# Record Class 1: slosh (shake half-full water bottle near mic)
python 01_collect_audio.py --class 1 --label slosh

# Record Class 2: siphon (suck water through rubber tube into glass)
python 01_collect_audio.py --class 2 --label siphon
```

Each command records 40 clips × 3 seconds. Press ENTER before each clip.

**Tips for good recordings:**
- Class 0: Run tap at different flow rates. Move mic closer/further.
- Class 1: Vary how vigorously you shake. Do it fast and slow.
- Class 2: THIS IS THE CRITICAL CLASS. Use a real rubber tube and glass of water.
  Suck the water through. Vary the speed. Also try blowing briefly.
  Record 50+ clips for this class if you can.
- Record in a somewhat quiet room. Turn off fans if possible.

#### Step 2 — Extract features (hours 2–4)
```bash
python 02_extract_features.py
# Output: data/features.csv and data/feature_params.json
```

#### Step 3 — Train model (hours 4–6)
```bash
python 03_train_model.py
# Output: models/fuel_model.pkl
# Check: accuracy should be ≥ 85%
```

**If accuracy < 85%:**
- Record 20 more siphon clips
- Re-run 02_extract_features.py and 03_train_model.py
- Siphon class is usually the weakest — more data always helps

---

### HOURS 0–6: Firmware Person

#### Step 1 — Open firmware in Arduino IDE
Open `bodashield/firmware/bodashield_esp32.ino`

#### Step 2 — Fill in credentials (top of file)
```cpp
const char* WIFI_SSID  = "YOUR_WIFI_SSID";      // your phone hotspot or venue WiFi
const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "https://xxxxx.ngrok.io"; // URL from backend person
```

#### Step 3 — Wire LEDs (optional but impressive)
```
ESP32 GPIO 2  → 220Ω resistor → GREEN LED → GND
ESP32 GPIO 5  → 220Ω resistor → RED LED   → GND
ESP32 GPIO 18 → 220Ω resistor → BLUE LED  → GND
ESP32 GPIO 4  → jumper wire (insert = ignition ON)
```
If you don't have LEDs, the sketch still works — LEDs are cosmetic.

#### Step 4 — Upload
- Tools → Board → ESP32 Dev Module
- Tools → Port → your COM port
- Click Upload (→ button)
- Open Serial Monitor (Tools → Serial Monitor, set to 115200 baud)
- Should see: "BodaShield ESP32 Firmware" and WiFi connecting

#### Step 5 — Test the HTTP bridge (hours 1–4)
In Serial Monitor, type and press Enter:
```
TEST
```
Should see: `[TEST] Firing test alert...` then `[OK] Server responded 200`
Also: the backend terminal should show the POST arriving.

#### Step 6 — Test serial command (hours 4–6)
In Serial Monitor, type:
```
SIPHON_DETECTED
```
Should see: red LED flash, HTTP POST, server receives it, phone rings (if AT Voice is configured).

---

### HOURS 0–6: Backend Person

#### Step 1 — Start server (hour 0)
```bash
cd bodashield/backend
python app.py
```

#### Step 2 — Verify endpoints with curl
```bash
# Test alert endpoint
curl -X POST http://localhost:5000/fuel_alert \
  -H "Content-Type: application/json" \
  -d '{"plate":"KCD123X","lat":-1.2921,"lng":36.8219,"confidence":0.92}'

# Test USSD
curl -X POST http://localhost:5000/ussd \
  -d "text=&phoneNumber=+254711000000&sessionId=abc"

# Test ingest
curl -X POST http://localhost:5000/ingest \
  -H "Content-Type: application/json" \
  -d '{"label":"siphon","confidence":0.91,"plate":"KCD123X"}'
```

#### Step 3 — Africa's Talking USSD simulator
1. Log into https://account.africastalking.com
2. Go to USSD → Simulator
3. Enter your USSD code, phone number
4. Test the full menu tree

#### Step 4 — Verify phone call works
```bash
curl -X POST http://localhost:5000/fuel_alert \
  -H "Content-Type: application/json" \
  -d '{"plate":"KCD123X","lat":-1.2921,"lng":36.8219,"confidence":0.95}'
```
Your phone should ring. If it doesn't:
- Check OWNER_PHONE is verified in AT sandbox
- Check AT_USERNAME and AT_API_KEY in .env
- Check AT account has credits (sandbox is free but needs setup)

---

### HOURS 6–14: Integration — connect everything

#### ML Person: Start live inference
```bash
cd ml/

# With ESP32 connected:
# Windows:
python 04_live_inference.py --port COM3
# Linux:
python 04_live_inference.py --port /dev/ttyUSB0

# Without ESP32 (testing only):
python 04_live_inference.py --no-serial
```

Find your COM port:
- Windows: Device Manager → Ports → look for "CP210x" or "CH340"
- Linux: `ls /dev/ttyUSB*` or `ls /dev/ttyACM*`
- Mac: `ls /dev/cu.usbserial*`

The visualiser window opens. Make sounds near your mic and watch the FFT graph update.

#### The full chain test (hour 8)
1. Start backend: `python app.py`
2. Start ngrok: `ngrok http 5000`
3. Upload firmware to ESP32 (with correct SERVER_URL)
4. Start inference: `python 04_live_inference.py --port COM3`
5. Open dashboard: http://localhost:5000/
6. Siphon water with your tube for 3+ seconds
7. Watch: FFT turns red → ESP32 LED turns red → YOUR PHONE RINGS

If it takes >10 seconds from siphon to phone ring:
- Edit `CONSECUTIVE_HITS = 2` in `04_live_inference.py` (was 3)
- This reduces detection window from 3s to 2s

---

### HOURS 14–28: Polish

#### ML: Engine knock model
Record additional audio:
```bash
# Class 3: healthy (fan, smooth motor near mic)
python 01_collect_audio.py --class 3 --label healthy

# Class 4: knock (tap mic rhythmically with a pen — like a bearing knock)
python 01_collect_audio.py --class 4 --label knock

# Re-extract and retrain
python 02_extract_features.py
python 03_train_model.py
```

Now the inference script detects both SIPHON and KNOCK.

#### Firmware: WiFi probe counting
In `bodashield_esp32.ino`, the WiFi probe counting code is in the `startProbeCount()` function.
To enable it, uncomment `startProbeCount()` in `setup()`.

Every 5 minutes it POSTs to `/passenger_count` with a unique phone count.
The backend reconciles this against expected fares and fires an SMS if there's a gap.

---

### HOURS 28–36: Pitch prep

Stop writing code. Run the full demo sequence 10 times.

#### Demo script (practice this until it's natural):

**[Backend person opens]** — 15 seconds:
> "Kenyan fleet operators lose KES 5 billion a year to fuel siphoning.
> Matatu owners lose 30 to 40 percent of fares to conductor fraud.
> We built one device that catches both. In real time. While you sleep."

**[ML person continues]** — 20 seconds:
> "This is an ESP32. Four dollars. It hides under the chassis.
> Our edge AI model runs directly on the chip — no cloud, no internet needed.
> It classifies acoustic signatures: pump hum, fuel slosh, and siphoning."

**[LIVE DEMO — ML person]**:
> "Watch the frequency graph. Normal. Normal. Now..." [insert tube, siphon water]
> "...the model detects the siphon frequency band. Three consecutive windows. Alert fires."

**[Phone rings — hold it up]**

**[Firmware person]** — 10 seconds:
> "That was a live AT Voice call to the fleet owner. It woke him up.
> An SMS with the GPS location already arrived. Evidence trail."

**[Backend person — USSD demo]**:
> "And this works on any phone." [dials *384*1#]
> "No smartphone. No data bundle. Any conductor's phone. Any Safaricom SIM."

**[Close]**:
> "KES 8,000 per vehicle, KES 500 a month.
> Payback in 6 weeks if we recover 15 percent of stolen fuel.
> That's BodaShield."

---

### HOURS 36–48: Stabilise

- DO NOT add new features
- Run demo 20 times, time it (target: < 5 minutes)
- If siphon detection fires >3/10 demo runs → keep it
- If siphon detection fires <5/10 → lower threshold to 0.70
- Label ESP32 board with masking tape
- Deploy backend to Railway or Render (free tier) for stable URL

#### Deploy to Railway (free):
```bash
# Install Railway CLI: https://docs.railway.app/develop/cli
railway login
cd bodashield/backend
railway init
railway up
# Get your stable URL — update SERVER_URL in firmware and re-upload
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: sounddevice` | `pip install sounddevice` — on Linux may need `sudo apt install libportaudio2` |
| Serial port not found | Windows: Device Manager → Ports. Linux: `ls /dev/ttyUSB*`. May need `sudo chmod 666 /dev/ttyUSB0` |
| ESP32 won't POST to ngrok | Add `http.setInsecure()` before `http.POST()` — already in firmware |
| Phone doesn't ring | Verify your number in AT sandbox dashboard at account.africastalking.com |
| USSD only works in simulator | Correct — AT sandbox USSD doesn't work on real SIM. Use simulator for demo, show on laptop screen |
| FFT visualiser won't open | Try `python 04_live_inference.py --no-plot` — inference still works without plot |
| Model accuracy < 85% | Record 20 more siphon clips. That class is almost always the weak one. |
| ngrok URL changes on restart | Use `ngrok http --subdomain=bodashield 5000` (paid plan) or deploy to Railway |

---

## File structure

```
bodashield/
├── requirements.txt
├── ml/
│   ├── 01_collect_audio.py    ← Record training audio
│   ├── 02_extract_features.py ← Extract FFT + MFCC features
│   ├── 03_train_model.py      ← Train RandomForest classifier
│   ├── 04_live_inference.py   ← Live mic → classify → alert
│   ├── data/                  ← Created by scripts
│   └── models/                ← Created by scripts
├── firmware/
│   └── bodashield_esp32.ino   ← Upload to ESP32
└── backend/
    ├── app.py                 ← Flask server (all endpoints)
    ├── .env.example           ← Copy to .env and fill in
    ├── bodashield.db          ← Created automatically on first run
    └── templates/
        ├── dashboard.html     ← Main dashboard UI
        └── pitch.html         ← ROI calculator
```
