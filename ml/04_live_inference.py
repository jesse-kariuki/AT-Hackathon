"""
STEP 4 — The live inference engine
Run this during the demo. It:
  - Streams mic audio in 1-second windows
  - Classifies each window (pump_hum / slosh / siphon / knock)
  - Shows a live FFT frequency visualiser with coloured bands
  - Sends SIPHON_DETECTED or KNOCK_DETECTED to ESP32 via serial
  - POSTs events to the Flask backend

Usage:
  python 04_live_inference.py --port COM3          # Windows
  python 04_live_inference.py --port /dev/ttyUSB0  # Linux
  python 04_live_inference.py --no-serial          # if ESP32 not connected yet

Fallback mode (no mic — play a .wav file instead):
  python 04_live_inference.py --file demo_siphon.wav --port COM3
"""

import argparse
import pickle
import json
import time
import threading
import queue
import numpy as np
import librosa
import scipy.io.wavfile as wav
from pathlib import Path
from collections import deque

# ── Optional imports — graceful fallback ─────────────────────────────────────
try:
    import sounddevice as sd
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False

# ── Config ───────────────────────────────────────────────────────────────────
SAMPLE_RATE      = 8000
WINDOW_SECS      = 1.0
N_MFCC           = 13
HOP_LENGTH       = 512
N_FFT            = 512
FFT_BANDS        = [(0, 80), (80, 200), (200, 800)]
CONFIDENCE_THRESH = 0.80
CONSECUTIVE_HITS  = 3       # windows in a row before firing alert
ALERT_COOLDOWN    = 15      # seconds between alerts
BACKEND_URL       = "http://localhost:5000"

LABEL_NAMES = {0: "pump_hum", 1: "slosh", 2: "SIPHON", 3: "healthy", 4: "KNOCK"}
LABEL_COLORS = {0: "green", 1: "grey", 2: "red", 3: "green", 4: "orange"}

# ── Shared state ─────────────────────────────────────────────────────────────
audio_queue      = queue.Queue()
last_alert_time  = 0
siphon_streak    = 0
knock_streak     = 0
history_conf     = {k: deque(maxlen=60) for k in LABEL_NAMES}
current_label    = 0
current_conf     = 0.0

# ─────────────────────────────────────────────────────────────────────────────

def hz_to_bin(hz):
    return int(hz * N_FFT / SAMPLE_RATE)

def extract_features(audio: np.ndarray) -> np.ndarray:
    audio = audio / (np.max(np.abs(audio)) + 1e-9)
    mfcc      = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=N_MFCC, hop_length=HOP_LENGTH)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std  = mfcc.std(axis=1)
    spectrum  = np.abs(np.fft.rfft(audio, n=N_FFT))
    band_feats = []
    for lo, hi in FFT_BANDS:
        band = spectrum[hz_to_bin(lo):hz_to_bin(hi)]
        band_feats.extend([band.mean(), band.std()])
    return np.concatenate([mfcc_mean, mfcc_std, band_feats])

def fire_alert(kind: str, confidence: float, ser):
    global last_alert_time
    now = time.time()
    if now - last_alert_time < ALERT_COOLDOWN:
        return
    last_alert_time = now

    print(f"\n ALERT: {kind} detected! confidence={confidence:.2f}")

    # Serial to ESP32
    if ser:
        try:
            ser.write(f"{kind}_DETECTED\n".encode())
            print(f"  → Sent '{kind}_DETECTED' to ESP32")
        except Exception as e:
            print(f"  ✗ Serial write failed: {e}")

    # POST to backend
    if HAS_REQUESTS:
        endpoint = "/fuel_alert" 
        try:
            requests.post(
                f"{BACKEND_URL}{endpoint}",
                json={"label": kind, "confidence": round(confidence, 3),
                      "plate": "KCD123X", "lat": -1.2921, "lng": 36.8219},
                timeout=3
            )
            print(f"  → POSTed to {endpoint}")
        except Exception as e:
            print(f"  ✗ Backend POST failed: {e}")

def inference_loop(fuel_bundle, engine_bundle, ser):
    global siphon_streak, knock_streak, current_label, current_conf

    fuel_model   = fuel_bundle["model"]
    fuel_scaler  = fuel_bundle["scaler"]
    engine_model = engine_bundle["model"]  if engine_bundle else None
    engine_scaler= engine_bundle["scaler"] if engine_bundle else None

    print("\n Listening... (Ctrl+C to stop)\n")

    while True:
        try:
            audio = audio_queue.get(timeout=2)
        except queue.Empty:
            continue

        try:
            feat = extract_features(audio)
            feat_scaled_fuel = fuel_scaler.transform([feat])

            pred_fuel = fuel_model.predict(feat_scaled_fuel)[0]
            prob_fuel = fuel_model.predict_proba(feat_scaled_fuel)[0].max()

            current_label = pred_fuel
            current_conf  = prob_fuel

            label_name = LABEL_NAMES.get(pred_fuel, "unknown")
            for k in history_conf:
                history_conf[k].append(0.0)
            history_conf[pred_fuel][-1] = prob_fuel

            print(f"  [{label_name:<10}] conf={prob_fuel:.2f}  {'█' * int(prob_fuel*20)}")



            # SIPHON — accept immediately (no confidence, no streaks)
            if pred_fuel == 2:
                fire_alert("SIPHON", prob_fuel, ser)

            # KNOCK — accept immediately (no confidence, no streaks)
            if pred_eng == 1:
                fire_alert("KNOCK", prob_eng, ser)

            

        except Exception as e:
            print(f"  ✗ Inference error: {e}")

def audio_callback(indata, frames, time_info, status):
    audio_queue.put(indata[:, 0].copy())

def stream_wav_file(filepath):
    """Fallback: play a wav file through the inference pipeline."""
    sr, data = wav.read(filepath)
    audio = data.astype(np.float32) / 32768.0
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
    chunk_size = int(SAMPLE_RATE * WINDOW_SECS)
    print(f"  Streaming {filepath} ({len(audio)/SAMPLE_RATE:.1f}s)")
    for i in range(0, len(audio) - chunk_size, chunk_size):
        audio_queue.put(audio[i:i+chunk_size])
        time.sleep(WINDOW_SECS)

def build_plot():
    """Build the live FFT visualiser dashboard."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    fig.patch.set_facecolor('#0d0d0d')
    fig.suptitle("BodaShield — Live Acoustic Monitor", color='white', fontsize=14, fontweight='bold')

    for ax in axes.flat:
        ax.set_facecolor('#1a1a1a')
        ax.tick_params(colors='#888')
        for spine in ax.spines.values():
            spine.set_color('#333')

    # Subplot 1: FFT spectrum
    ax_fft = axes[0, 0]
    ax_fft.set_title("Frequency Spectrum", color='#aaa', fontsize=10)
    ax_fft.set_xlabel("Hz", color='#888')
    ax_fft.set_ylabel("Magnitude", color='#888')
    freqs = np.fft.rfftfreq(N_FFT, 1/SAMPLE_RATE)
    line_fft, = ax_fft.plot(freqs, np.zeros(len(freqs)), color='#00ff88', lw=1)
    # Band shading
    for (lo, hi), col in zip(FFT_BANDS, ['#1a3a1a', '#3a3a1a', '#3a1a1a']):
        ax_fft.axvspan(lo, hi, alpha=0.3, color=col)
    ax_fft.set_xlim(0, 1000)

    # Subplot 2: Classification confidence bars
    ax_conf = axes[0, 1]
    ax_conf.set_title("Classification Confidence", color='#aaa', fontsize=10)
    bar_colors = ['#00ff88', '#888888', '#ff3333']
    bars = ax_conf.bar(
        ['pump_hum', 'slosh', 'SIPHON'],
        [0, 0, 0],
        color=bar_colors
    )
    ax_conf.set_ylim(0, 1)
    ax_conf.tick_params(colors='#888')
    ax_conf.axhline(CONFIDENCE_THRESH, color='yellow', linestyle='--', alpha=0.5, lw=1)

    # Subplot 3: Confidence history (rolling 60s)
    ax_hist = axes[1, 0]
    ax_hist.set_title("Confidence History (60s)", color='#aaa', fontsize=10)
    ax_hist.set_ylim(0, 1)
    ax_hist.set_xlim(0, 60)
    lines_hist = {}
    for label_int, name in {0:'pump_hum',1:'slosh',2:'SIPHON'}.items():
        col = ['#00ff88','#888','#ff3333'][label_int]
        ln, = ax_hist.plot([], [], color=col, lw=1.5, label=name)
        lines_hist[label_int] = ln
    ax_hist.legend(fontsize=8, labelcolor='#aaa', facecolor='#1a1a1a', framealpha=0.5)

    # Subplot 4: Status panel
    ax_status = axes[1, 1]
    ax_status.set_title("System Status", color='#aaa', fontsize=10)
    ax_status.axis('off')
    status_text = ax_status.text(
        0.5, 0.5, "ARMED\nListening...",
        ha='center', va='center', fontsize=18, fontweight='bold',
        color='#00ff88', transform=ax_status.transAxes
    )

    latest_audio = [np.zeros(int(SAMPLE_RATE * WINDOW_SECS))]

    def audio_cb_plot(indata, frames, time_info, status_sd):
        latest_audio[0] = indata[:, 0].copy()
        audio_queue.put(indata[:, 0].copy())

    def update(_frame):
        audio = latest_audio[0]
        spectrum = np.abs(np.fft.rfft(audio, n=N_FFT))
        line_fft.set_ydata(spectrum)
        ax_fft.set_ylim(0, max(spectrum.max(), 0.01))

        # Update confidence bars using latest inference result
        proba = [0.0, 0.0, 0.0]
        proba[min(current_label, 2)] = current_conf
        for bar, p in zip(bars, proba):
            bar.set_height(p)

        # History lines
        for label_int, ln in lines_hist.items():
            vals = list(history_conf[label_int])
            if vals:
                ln.set_data(range(len(vals)), vals)

        # Status text
        label_name = LABEL_NAMES.get(current_label, "?")
        if current_label == 2 and current_conf >= CONFIDENCE_THRESH:
            status_text.set_text(" SIPHON\nDETECTED")
            status_text.set_color('#ff3333')
            ax_status.set_facecolor('#2a0000')
        else:
            status_text.set_text(f"ARMED\n{label_name}\n{current_conf:.0%}")
            status_text.set_color('#00ff88')
            ax_status.set_facecolor('#1a1a1a')

        return [line_fft, status_text] + list(bars)

    plt.tight_layout()
    return fig, audio_cb_plot, update

# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BodaShield Live Inference")
    parser.add_argument("--port",       default=None,  help="Serial port for ESP32 (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud",       default=115200, type=int)
    parser.add_argument("--no-serial",  action="store_true")
    parser.add_argument("--file",       default=None,  help="Play a .wav file instead of mic input")
    parser.add_argument("--no-plot",    action="store_true")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  BodaShield — Live Inference Engine")
    print("="*50)

    # Load models
    fuel_bundle   = None
    engine_bundle = None
    for name, path in [("fuel", "models/fuel_model.pkl"), ("engine", "models/engine_model.pkl")]:
        if Path(path).exists():
            with open(path, "rb") as f:
                bundle = pickle.load(f)
            if name == "fuel":
                fuel_bundle = bundle
            else:
                engine_bundle = bundle
            print(f"   Loaded {name} model")
        else:
            print(f"  ⚠ {path} not found — run 03_train_model.py first")

    if fuel_bundle is None:
        print("\n  ERROR: fuel model required. Exiting.")
        return

    # Serial connection
    ser = None
    if not args.no_serial and args.port:
        if HAS_SERIAL:
            try:
                ser = serial.Serial(args.port, args.baud, timeout=1)
                print(f"   Serial connected: {args.port}")
            except Exception as e:
                print(f"  ⚠ Serial failed ({e}) — continuing without ESP32")
        else:
            print("  ⚠ pyserial not installed — no ESP32 connection")
    else:
        print("  ℹ Running without serial (--no-serial or no --port given)")

    # Start inference thread
    t = threading.Thread(
        target=inference_loop,
        args=(fuel_bundle, engine_bundle, ser),
        daemon=True
    )
    t.start()

    # Audio source
    if args.file:
        threading.Thread(target=stream_wav_file, args=(args.file,), daemon=True).start()

    # Plot
    if HAS_PLOT and not args.no_plot and HAS_SOUND:
        fig, audio_cb_plot, update_fn = build_plot()
        if not args.file:
            stream = sd.InputStream(
                callback=audio_cb_plot,
                samplerate=SAMPLE_RATE,
                channels=1,
                blocksize=int(SAMPLE_RATE * WINDOW_SECS)
            )
            stream.start()
        ani = animation.FuncAnimation(fig, update_fn, interval=100, blit=False)
        plt.show()
    elif HAS_SOUND and not args.file:
        # No plot — just stream
        with sd.InputStream(
            callback=audio_callback,
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=int(SAMPLE_RATE * WINDOW_SECS)
        ):
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n  Stopped.")
    else:
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n  Stopped.")

if __name__ == "__main__":
    main()
