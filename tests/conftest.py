from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ["DB_PATH"] = str(ROOT_DIR / "data" / "test_state.sqlite3")
os.environ.setdefault("MODEL_DIR", str(ROOT_DIR / "ml" / "models"))
os.environ.setdefault("GROQ_API_KEY", "")

from api.main import app  # noqa: E402
from api.store import reset_store  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    reset_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_store()
