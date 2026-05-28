"""
STEP 1 - RUN THIS FIRST
Records audio clips for training.
Run this script 3 times, once per class.

Usage:
  python 01_collect_audio.py --class 0 --label pump_hum
  python 01_collect_audio.py --class 1 --label slosh
  python 01_collect_audio.py --class 2 --label siphon

For each class, the script records 40 clips of 3 seconds each.
Press ENTER to start each clip. Press Ctrl+C to stop early.
"""

import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import argparse
import os
import time

SAMPLE_RATE = 8000
DURATION    = 3       # seconds per clip
N_CLIPS     = 40
OUTPUT_DIR  = "data/raw"

def record_clip(clip_index, class_label, label_name):
    os.makedirs(f"{OUTPUT_DIR}/{label_name}", exist_ok=True)
    filepath = f"{OUTPUT_DIR}/{label_name}/clip_{clip_index:03d}.wav"

    input(f"  Clip {clip_index+1}/{N_CLIPS} — press ENTER then make the '{label_name}' sound for {DURATION}s ...")
    print("  Recording...", end="", flush=True)

    audio = sd.rec(
        int(SAMPLE_RATE * DURATION),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32'
    )
    sd.wait()
    print(" done.")

    audio = audio / (np.max(np.abs(audio)) + 1e-9)
    wav.write(filepath, SAMPLE_RATE, (audio * 32767).astype(np.int16))
    print(f"  Saved → {filepath}")
    return filepath

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--class",  type=int,  required=True, dest="cls",   help="0=pump_hum, 1=slosh, 2=siphon")
    parser.add_argument("--label",  type=str,  required=True, dest="label", help="human-readable label")
    parser.add_argument("--clips",  type=int,  default=N_CLIPS)
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  BodaShield — Audio Collection")
    print(f"  Class {args.cls}: {args.label}")
    print(f"  Recording {args.clips} clips × {DURATION}s @ {SAMPLE_RATE}Hz")
    print(f"{'='*50}\n")

    print("Instructions per class:")
    print("  Class 0 (pump_hum) → run a tap near your laptop mic")
    print("  Class 1 (slosh)    → shake a half-full water bottle near mic")
    print("  Class 2 (siphon)   → suck water through a rubber tube into a glass\n")

    for i in range(args.clips):
        record_clip(i, args.cls, args.label)
        time.sleep(0.5)

    print(f"\n Done. {args.clips} clips saved to {OUTPUT_DIR}/{args.label}/")

if __name__ == "__main__":
    main()
