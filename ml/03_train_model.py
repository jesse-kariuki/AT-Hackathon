"""
STEP 3 — Train the classifier
Run after 02_extract_features.py

Usage:
  python 03_train_model.py

Outputs:
  models/fuel_model.pkl        — RandomForest for fuel theft detection
  models/engine_model.pkl      — RandomForest for engine knock detection
  models/training_report.txt   — accuracy + confusion matrix
"""

import pickle
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler

FEATURES_CSV   = Path("data/features.csv")
PARAMS_JSON    = Path("data/feature_params.json")
MODELS_DIR     = Path("models")
REPORT_PATH    = Path("models/training_report.txt")


FUEL_LABELS   = [0, 1, 2]
ENGINE_LABELS = [3, 4]

def train(df, labels, name):
    subset = df[df["label"].isin(labels)].copy()
    if len(subset) == 0:
        print(f"  ⚠ No data found for {name} labels {labels} — skipping")
        return None, None

    label_remap = {l: i for i, l in enumerate(sorted(labels))}
    subset["label"] = subset["label"].map(label_remap)

    X = subset.drop("label", axis=1).values
    y = subset["label"].values

    scaler = StandardScaler()
    X = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_split=2,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_pred    = model.predict(X_test)
    acc       = (y_pred == y_test).mean()
    cv_scores = cross_val_score(model, X, y, cv=5)

    report = (
        f"\n{'='*50}\n"
        f"  {name}\n"
        f"{'='*50}\n"
        f"  Test accuracy : {acc*100:.1f}%\n"
        f"  CV mean       : {cv_scores.mean()*100:.1f}% ± {cv_scores.std()*100:.1f}%\n"
        f"  Training size : {len(X_train)}\n"
        f"  Test size     : {len(X_test)}\n\n"
        f"Classification report:\n"
        f"{classification_report(y_test, y_pred)}\n"
        f"Confusion matrix:\n"
        f"{confusion_matrix(y_test, y_pred)}\n"
    )
    print(report)

    if acc < 0.85:
        print(f"   WARNING: accuracy {acc*100:.1f}% < 85%.")
        print("  → Record more audio clips, especially the borderline class.")
        print("  → Try collecting clips in a quieter environment.")

    return model, scaler, report, label_remap

def main():
    MODELS_DIR.mkdir(exist_ok=True)

    print("\n BodaShield — Model Training\n")

    if not FEATURES_CSV.exists():
        print("ERROR: data/features.csv not found. Run 02_extract_features.py first.")
        return

    df = pd.read_csv(FEATURES_CSV)
    print(f"  Loaded {len(df)} samples, {df['label'].nunique()} classes\n")
    print("  Label distribution:")
    print(df["label"].value_counts().to_string())
    print()

    all_reports = ""

    # ── Fuel model ────────────────────────────────────────────────────────────
    result = train(df, FUEL_LABELS, "FUEL GUARD MODEL (pump/slosh/siphon)")
    if result[0] is not None:
        model, scaler, report, remap = result
        all_reports += report
        with open(MODELS_DIR / "fuel_model.pkl", "wb") as f:
            pickle.dump({"model": model, "scaler": scaler, "label_remap": remap}, f)
        print(f" Saved → models/fuel_model.pkl")

    # ── Engine model ──────────────────────────────────────────────────────────
    result = train(df, ENGINE_LABELS, "ENGINE KNOCK MODEL (healthy/knock)")
    if result[0] is not None:
        model, scaler, report, remap = result
        all_reports += report
        with open(MODELS_DIR / "engine_model.pkl", "wb") as f:
            pickle.dump({"model": model, "scaler": scaler, "label_remap": remap}, f)
        print(f"   Saved → models/engine_model.pkl")

    # Save report
    with open(REPORT_PATH, "w") as f:
        f.write(all_reports)
    print(f"\n  Full report → {REPORT_PATH}")
    print("\n  Next step: run 04_live_inference.py")

if __name__ == "__main__":
    main()
