from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"

BENIGN_HINTS = ("benign", "normal")

_MODEL: RandomForestClassifier | None = None
_SCALER: StandardScaler | None = None
_FEATURE_COLUMNS: list[str] | None = None


def _infer_label_from_path(csv_path: Path) -> int:
    normalized = str(csv_path).lower()
    return 0 if any(hint in normalized for hint in BENIGN_HINTS) else 1


def load_dataset(dataset_dir: str | Path, max_rows: int = 100000) -> pd.DataFrame:
    dataset_path = Path(dataset_dir).expanduser().resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_path}")

    csv_files = sorted(dataset_path.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under: {dataset_path}")
    csv_files = [f for f in csv_files if re.search(r"\.(benign|mirai|gafgyt)", f.name)]
    if not csv_files:
        raise FileNotFoundError(
            f"No N-BaIoT traffic CSV files found under: {dataset_path}"
        )

    rows_per_file = max(1, max_rows // len(csv_files))
    frames: list[pd.DataFrame] = []

    for csv_file in csv_files:
        frame = pd.read_csv(csv_file, nrows=rows_per_file)
        if frame.empty:
            continue

        label = _infer_label_from_path(csv_file)
        frame = pd.concat([frame, pd.Series([label] * len(frame), name="label")], axis=1)
        frames.append(frame)

    if not frames:
        raise ValueError("All CSV files were empty.")

    dataset = pd.concat(frames, ignore_index=True)
    class_counts = dataset["label"].value_counts().sort_index()

    print("Loaded dataset:")
    print(f"  Total rows: {len(dataset)}")
    print("  Class distribution:")
    for label, count in class_counts.items():
        print(f"    label={label}: {count}")

    return dataset


def preprocess_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    if "label" not in dataset.columns:
        raise ValueError("Dataset must contain a 'label' column.")

    labels = dataset["label"].astype(int)
    features = dataset.drop(columns=["label"]).copy()

    for column in features.columns:
        features[column] = pd.to_numeric(features[column], errors="coerce", downcast="float")

    cleaned = features.replace([np.inf, -np.inf], np.nan).fillna(0)
    dropped_rows = len(dataset) - len(cleaned)
    if dropped_rows:
        print(f"Dropped {dropped_rows} rows containing null or infinite values.")

    if cleaned.empty:
        raise ValueError("No rows remaining after dropping null/infinite values.")

    labels = labels.loc[cleaned.index]

    non_numeric_columns = cleaned.select_dtypes(exclude=[np.number]).columns.tolist()
    if non_numeric_columns:
        raise ValueError(
            "All training features must be numeric. "
            f"Non-numeric columns found: {non_numeric_columns}"
        )

    return cleaned, labels


def train(dataset_dir: str | Path) -> dict[str, Any]:
    dataset = load_dataset(dataset_dir)

    # DEBUG
    sample = dataset.head(1000).copy()
    sample = sample.apply(pd.to_numeric, errors="coerce")
    print(
        "Inf count:",
        np.isinf(sample.select_dtypes(include=[np.number])).sum().sum(),
    )
    print("NaN count:", sample.isnull().sum().sum())
    print("Total cells:", sample.size)
    cols_with_inf = sample.columns[
        np.isinf(sample.select_dtypes(include=[np.number])).any()
    ].tolist()
    print("Columns with inf:", cols_with_inf[:10])

    features, labels = preprocess_dataset(dataset)

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)

    scaler.feature_columns_ = list(features.columns)

    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(x_train_scaled, y_train)

    predictions = model.predict(x_test_scaled)

    print("\nClassification report:")
    print(classification_report(y_test, predictions, digits=4))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    print(f"Saved model to: {MODEL_PATH}")
    print(f"Saved scaler to: {SCALER_PATH}")

    global _MODEL, _SCALER, _FEATURE_COLUMNS
    _MODEL = model
    _SCALER = scaler
    _FEATURE_COLUMNS = list(scaler.feature_columns_)

    return {
        "model_path": MODEL_PATH,
        "scaler_path": SCALER_PATH,
        "feature_count": len(_FEATURE_COLUMNS),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
    }


def _load_artifacts() -> tuple[RandomForestClassifier, StandardScaler, list[str]]:
    global _MODEL, _SCALER, _FEATURE_COLUMNS

    if _MODEL is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model artifact not found: {MODEL_PATH}")
        _MODEL = joblib.load(MODEL_PATH)
        if hasattr(_MODEL, "n_jobs"):
            _MODEL.n_jobs = 1

    if _SCALER is None:
        if not SCALER_PATH.exists():
            raise FileNotFoundError(f"Scaler artifact not found: {SCALER_PATH}")
        _SCALER = joblib.load(SCALER_PATH)

    if _FEATURE_COLUMNS is None:
        feature_columns = getattr(_SCALER, "feature_columns_", None)
        if not feature_columns:
            raise ValueError(
                "Scaler artifact is missing feature metadata required for inference."
            )
        _FEATURE_COLUMNS = list(feature_columns)

    return _MODEL, _SCALER, _FEATURE_COLUMNS


def predict(features: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(features, dict):
        raise TypeError("features must be provided as a dictionary.")

    model, scaler, feature_columns = _load_artifacts()

    missing_features = [column for column in feature_columns if column not in features]
    if missing_features:
        preview = ", ".join(missing_features[:10])
        suffix = "..." if len(missing_features) > 10 else ""
        raise ValueError(f"Missing required features: {preview}{suffix}")

    ordered_values = {column: features[column] for column in feature_columns}
    input_frame = pd.DataFrame([ordered_values], columns=feature_columns)
    input_frame = input_frame.replace([np.inf, -np.inf], np.nan)

    if input_frame.isnull().any().any():
        bad_columns = input_frame.columns[input_frame.isnull().any()].tolist()
        raise ValueError(f"Input contains null or infinite values for: {bad_columns}")

    non_numeric_columns = input_frame.select_dtypes(exclude=[np.number]).columns.tolist()
    if non_numeric_columns:
        raise ValueError(
            "All inference features must be numeric. "
            f"Non-numeric columns found: {non_numeric_columns}"
        )

    scaled_input = scaler.transform(input_frame)
    if hasattr(model, "n_jobs"):
        model.n_jobs = 1
    predicted_label = int(model.predict(scaled_input)[0])
    probabilities = model.predict_proba(scaled_input)[0]
    confidence = float(probabilities[predicted_label])

    return {
        "label": predicted_label,
        "confidence": confidence,
        "is_anomaly": bool(predicted_label == 1),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train a Random Forest anomaly detector on the N-BaIoT dataset."
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to the root directory containing N-BaIoT CSV files.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    train(args.data_dir)
