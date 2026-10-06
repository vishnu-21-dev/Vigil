from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_model_dir() -> str:
    raw = os.getenv("MODEL_DIR")
    if not raw:
        return str(PROJECT_ROOT / "ml" / "models")
    path = Path(raw).expanduser()
    return str(path if path.is_absolute() else (PROJECT_ROOT / path).resolve())


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    model_dir: str = _resolve_model_dir()
    db_path: str = os.getenv("DB_PATH", "data/app_state.sqlite3")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b"


settings = Settings()
