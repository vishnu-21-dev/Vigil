from __future__ import annotations

from typing import Any


def run_inference(features: dict[str, Any]) -> dict[str, Any]:
    try:
        import ml.pipeline as pipeline
        from pathlib import Path

        from api.config import settings

        model_dir = Path(settings.model_dir).resolve()
        pipeline.MODEL_DIR = model_dir
        pipeline.MODEL_PATH = model_dir / "model.pkl"
        pipeline.SCALER_PATH = model_dir / "scaler.pkl"

        return pipeline.predict(features)
    except Exception as e:
        return {"error": f"model not loaded: {e}"}
