from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "data" / "ibs_fighter.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


load_local_env()

HOST = os.environ.get("IBS_FIGHTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBS_FIGHTER_PORT", "8765"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MEAL_MODEL = os.environ.get("OPENAI_MEAL_MODEL", "gpt-5.4-mini")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
