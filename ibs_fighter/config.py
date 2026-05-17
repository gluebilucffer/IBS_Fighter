from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "ibs_fighter.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"

HOST = os.environ.get("IBS_FIGHTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBS_FIGHTER_PORT", "8765"))

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
