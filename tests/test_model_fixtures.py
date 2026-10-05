from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.ml_bridge import run_inference


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _require_model_files():
    from api.config import settings

    model_dir = Path(settings.model_dir)
    missing = [name for name in ("model.pkl", "scaler.pkl") if not (model_dir / name).exists()]
    if missing:
        pytest.skip(
            f"model artifacts not found in {model_dir} ({', '.join(missing)}); "
            "train with `python -m ml.pipeline --data-dir <N-BaIoT dir>` or set MODEL_DIR"
        )


def _classify(name: str) -> dict:
    features = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    result = run_inference(features)
    assert "error" not in result, result
    print(f"{name}: is_anomaly={result['is_anomaly']} confidence={result['confidence']:.4f}")
    return result


def test_mirai_fixture_is_classified_as_anomaly():
    assert _classify("mirai_ack_row.json")["is_anomaly"] is True


def test_benign_fixture_is_classified_as_normal():
    assert _classify("benign_row.json")["is_anomaly"] is False
