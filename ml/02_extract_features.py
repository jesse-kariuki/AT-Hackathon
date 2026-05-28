"""
STEP 2 — Run after collecting audio
Extracts features from all .wav files and builds a CSV for training.

Usage:
  python 02_extract_features.py

Output:
  data/features.csv  (one row per clip, columns = features + label)
  data/feature_params.json  (params to use at inference time — give this to backend person)
"""

import os
import json
import numpy as np
import pandas as pd
import librosa
import scipy.io.wavfile as wav
from pathlib import Path

SAMPLE_RATE   = 8000
N_MFCC        = 13
WINDOW_LEN    = 3.0        # seconds
HOP_LENGTH    = 512
FFT_BANDS     = [(0, 80), (80, 200), (200, 800)]   # Hz ranges

LABEL_MAP = {
    "pump_hum": 0,
    "slosh":    1,
    "siphon":   2,
    "healthy":  3,    # engine knock classifier class 0
    "knock":    4,    # engine knock classifier class 1
}

RAW_DIR = Path("data/raw")
OUT_CSV = Path("data/features.csv")
OUT_PARAMS = Path("data/feature_params.json")


def hz_to_bin(hz, n_fft):
    """Convert Hz to FFT bin index."""
    return int(hz * n_fft / SAMPLE_RATE)

def extract_features(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    Returns a 1D feature vector of length:
      13 MFCCs (mean) + 13 MFCCs (std)
      + 3 bands × 2 stats (mean, std) = 6
      Total = 32 features
    """
    if sr != SAMPLE_RATE:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    
    audio = audio / (np.max(np.abs(audio)) + 1e-9)

    # MFCCs
    mfcc = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=N_MFCC, hop_length=HOP_LENGTH)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std  = mfcc.std(axis=1)

    # FFT magnitude spectrum
    n_fft   = 512
    spectrum = np.abs(np.fft.rfft(audio, n=n_fft))

    band_features = []
    for lo_hz, hi_hz in FFT_BANDS:
        lo_bin = hz_to_bin(lo_hz, n_fft)
        hi_bin = hz_to_bin(hi_hz, n_fft)
        band   = spectrum[lo_bin:hi_bin]
        band_features.extend([band.mean(), band.std()])

    return np.concatenate([mfcc_mean, mfcc_std, band_features])

def process_all():
    rows = []

    for label_dir in sorted(RAW_DIR.iterdir()):
        if not label_dir.is_dir():
            continue
        label_name = label_dir.name
        if label_name not in LABEL_MAP:
            print(f"  ⚠ Unknown label dir '{label_name}' — skipping")
            continue
        label_int = LABEL_MAP[label_name]

        wav_files = list(label_dir.glob("*.wav"))
        print(f"  Processing {len(wav_files)} clips for '{label_name}' (label={label_int})")

        for wav_path in wav_files:
            try:
                sr, data = wav.read(str(wav_path))
                audio = data.astype(np.float32)
                if audio.max() > 1.0:
                    audio /= 32768.0
                feat = extract_features(audio, sr)
                rows.append(list(feat) + [label_int])
            except Exception as e:
                print(f"    ✗ {wav_path.name}: {e}")

    mfcc_cols = [f"mfcc_{i}_mean" for i in range(N_MFCC)] + \
                [f"mfcc_{i}_std"  for i in range(N_MFCC)]
    band_cols = []
    for lo, hi in FFT_BANDS:
        band_cols += [f"band_{lo}_{hi}_mean", f"band_{lo}_{hi}_std"]
    cols = mfcc_cols + band_cols + ["label"]

    df = pd.DataFrame(rows, columns=cols)
    OUT_CSV.parent.mkdir(exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\n Saved {len(df)} rows → {OUT_CSV}")

    params = {
        "sample_rate":  SAMPLE_RATE,
        "n_mfcc":       N_MFCC,
        "window_len":   WINDOW_LEN,
        "hop_length":   HOP_LENGTH,
        "n_fft":        512,
        "fft_bands":    FFT_BANDS,
        "label_map":    {v: k for k, v in LABEL_MAP.items()},
        "n_features":   len(cols) - 1,
    }
    with open(OUT_PARAMS, "w") as f:
        json.dump(params, f, indent=2)
    print(f" Saved feature params → {OUT_PARAMS}")
    print(f"\n Give feature_params.json to the backend person.")

if __name__ == "__main__":
    print("\n BodaShield — Feature Extraction\n")
    process_all()
