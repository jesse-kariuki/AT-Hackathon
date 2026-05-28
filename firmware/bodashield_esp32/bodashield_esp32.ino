/*
  BodaShield ESP32 Firmware
  ─────────────────────────
  What this does:
    1. Connects to WiFi
    2. Listens on USB Serial for commands from the ML laptop script
    3. When it receives "SIPHON_DETECTED" or "KNOCK_DETECTED":
       - Fires an HTTP POST to your Flask backend
    4. LED status:
       - Green blink (every 2s)  = armed, listening
       - Solid red               = alert firing
       - Blue flash              = server confirmed (200 OK)
    5. Ignition simulation:
       - Pin 4 HIGH (jumper in)  = ignition ON  → suppress siphon alerts
       - Pin 4 LOW               = ignition OFF → alerts active

  How to use:
    1. Open in Arduino IDE (or PlatformIO)
    2. Fill in WIFI_SSID, WIFI_PASS, SERVER_URL below
    3. Install boards: "ESP32 by Espressif" in Board Manager
    4. Select board: "ESP32 Dev Module"
    5. Upload
    6. Open Serial Monitor @ 115200 baud to see status

  Wiring:
    - Green LED  → GPIO 2  (with 220Ω resistor to GND)
    - Red LED    → GPIO 5  (with 220Ω resistor to GND)
    - Blue LED   → GPIO 18 (with 220Ω resistor to GND)
    - Ignition   → GPIO 4  (jumper wire: insert = ignition ON)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ── CONFIGURE THESE ───────────────────────────────────────────────────────────
const char* WIFI_SSID   = "YOUR_WIFI_SSID";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";

// Your ngrok URL (no trailing slash). E.g.: "https://abc123.ngrok.io"
const char* SERVER_URL  = "https://YOUR_NGROK_URL_HERE";

// Vehicle identity (shown in alerts)
const char* PLATE       = "KCD123X";
// Fake GPS coords for demo (Nairobi CBD)
const float LAT         = -1.2921;
const float LNG         = 36.8219;
// ─────────────────────────────────────────────────────────────────────────────

// Pin definitions
#define PIN_LED_GREEN  2
#define PIN_LED_RED    5
#define PIN_LED_BLUE   18
#define PIN_IGNITION   4

// Timing
#define WIFI_TIMEOUT_MS     15000
#define HTTP_TIMEOUT_MS     5000
#define BLINK_INTERVAL_MS   2000
#define SERIAL_BAUD         115200

// State
String  serialBuffer = "";
bool    wifiConnected = false;
unsigned long lastBlink = 0;

// ─────────────────────────────────────────────────────────────────────────────

void setLED(int r, int g, int b) {
  digitalWrite(PIN_LED_RED,   r ? HIGH : LOW);
  digitalWrite(PIN_LED_GREEN, g ? HIGH : LOW);
  digitalWrite(PIN_LED_BLUE,  b ? HIGH : LOW);
}

void blinkLED(int pin, int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH); delay(delayMs);
    digitalWrite(pin, LOW);  delay(delayMs);
  }
}

void connectWiFi() {
  Serial.printf("\nConnecting to WiFi '%s'", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) {
      Serial.println("\n[ERR] WiFi timeout — check credentials");
      setLED(1, 0, 0);  
      return;
    }
    delay(500);
    Serial.print(".");
    blinkLED(PIN_LED_GREEN, 1, 100);
  }
  wifiConnected = true;
  Serial.printf("\n[OK] WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
  blinkLED(PIN_LED_BLUE, 3, 150);  // triple blue = connected
}

bool postAlert(const char* alertType, float confidence) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WARN] WiFi not connected — attempting reconnect");
    connectWiFi();
    if (!wifiConnected) return false;
  }

  // Choose endpoint
  String endpoint = String(SERVER_URL);
  if (String(alertType) == "SIPHON") {
    endpoint += "/fuel_alert";
  } else if (String(alertType) == "KNOCK") {
    endpoint += "/engine_alert";
  } else {
    endpoint += "/trigger_alert";
  }

  // Build JSON payload
  StaticJsonDocument<256> doc;
  doc["alert_type"]  = alertType;
  doc["plate"]       = PLATE;
  doc["lat"]         = LAT;
  doc["lng"]         = LNG;
  doc["confidence"]  = confidence;
  doc["ignition"]    = (digitalRead(PIN_IGNITION) == HIGH);

  String payload;
  serializeJson(doc, payload);

  Serial.printf("[POST] %s → %s\n", alertType, endpoint.c_str());
  Serial.printf("       Payload: %s\n", payload.c_str());

  // LED: solid red while sending
  setLED(1, 0, 0);

  HTTPClient http;
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);

  // For demo: disable SSL certificate check (ngrok free tier)
  // In production: remove this and use proper certs
  http.setInsecure();

  int code = http.POST(payload);

  if (code == 200) {
    Serial.printf("[OK] Server responded 200\n");
    setLED(0, 0, 0);
    blinkLED(PIN_LED_BLUE, 4, 100);  // 4 blue flashes = success
    http.end();
    return true;
  } else {
    Serial.printf("[ERR] HTTP %d — %s\n", code, http.getString().c_str());
    setLED(1, 0, 0);  // stay red on failure
    http.end();
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(500);

  // LED pins
  pinMode(PIN_LED_GREEN,  OUTPUT);
  pinMode(PIN_LED_RED,    OUTPUT);
  pinMode(PIN_LED_BLUE,   OUTPUT);
  pinMode(PIN_IGNITION,   INPUT_PULLDOWN);  // LOW when no jumper

  setLED(0, 0, 0);

  Serial.println("\n==============================");
  Serial.println("  BodaShield ESP32 Firmware");
  Serial.println("==============================");

  connectWiFi();

  Serial.println("\nReady. Waiting for ML script commands on Serial.");
  Serial.println("Commands: SIPHON_DETECTED | KNOCK_DETECTED | STATUS | TEST");
  Serial.println("Ignition pin (GPIO 4): insert jumper = ignition ON\n");
}

void loop() {
  // ── Heartbeat blink ───────────────────────────────────────────────────────
  if (millis() - lastBlink > BLINK_INTERVAL_MS) {
    lastBlink = millis();
    bool ignitionOn = digitalRead(PIN_IGNITION) == HIGH;
    if (ignitionOn) {
      blinkLED(PIN_LED_GREEN, 2, 80);   // double blink = ignition on
    } else {
      blinkLED(PIN_LED_GREEN, 1, 80);   // single blink = armed, ignition off
    }
  }

  // ── Serial reader ─────────────────────────────────────────────────────────
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      serialBuffer.trim();
      processCommand(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }

  // ── WiFi watchdog ─────────────────────────────────────────────────────────
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    connectWiFi();
  }

  delay(10);
}

void processCommand(String cmd) {
  Serial.printf("[CMD] Received: '%s'\n", cmd.c_str());

  // ── STATUS query ──────────────────────────────────────────────────────────
  if (cmd == "STATUS") {
    bool ign = digitalRead(PIN_IGNITION) == HIGH;
    Serial.printf("[STATUS] WiFi=%s | Ignition=%s | Plate=%s\n",
      WiFi.isConnected() ? "OK" : "FAIL",
      ign ? "ON" : "OFF",
      PLATE
    );
    blinkLED(PIN_LED_BLUE, 2, 100);
    return;
  }

  // ── TEST — fire a dummy alert ─────────────────────────────────────────────
  if (cmd == "TEST") {
    Serial.println("[TEST] Firing test alert...");
    postAlert("TEST", 0.99);
    return;
  }

  // ── SIPHON_DETECTED ───────────────────────────────────────────────────────
  if (cmd.startsWith("SIPHON_DETECTED")) {
    bool ignitionOn = digitalRead(PIN_IGNITION) == HIGH;
    if (ignitionOn) {
      Serial.println("[SIPHON] Suppressed — ignition is ON (fuel pump running normally)");
      return;
    }
    // Parse confidence if provided (format: "SIPHON_DETECTED:0.94")
    float conf = 0.90;
    int colonIdx = cmd.indexOf(':');
    if (colonIdx >= 0) {
      conf = cmd.substring(colonIdx + 1).toFloat();
    }
    Serial.printf("[SIPHON] ALERT! Confidence=%.2f | Ignition=OFF → Firing!\n", conf);
    postAlert("SIPHON", conf);
    return;
  }

  // ── KNOCK_DETECTED ────────────────────────────────────────────────────────
  if (cmd.startsWith("KNOCK_DETECTED")) {
    float conf = 0.88;
    int colonIdx = cmd.indexOf(':');
    if (colonIdx >= 0) {
      conf = cmd.substring(colonIdx + 1).toFloat();
    }
    Serial.printf("[KNOCK] ALERT! Confidence=%.2f → Firing!\n", conf);
    postAlert("KNOCK", conf);
    return;
  }

  // ── Unknown ───────────────────────────────────────────────────────────────
  Serial.printf("[WARN] Unknown command: '%s'\n", cmd.c_str());
}
