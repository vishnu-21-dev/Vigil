from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    model_dir: str = os.getenv("MODEL_DIR", r"C:\Users\vishn\Downloads\Cyber\ml\models")
    db_path: str = os.getenv("DB_PATH", "data/app_state.sqlite3")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")


settings = Settings()
