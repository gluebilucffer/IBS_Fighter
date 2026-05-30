from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


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


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)

IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
DATA_DIR = Path(os.environ.get("IBS_FIGHTER_DATA_DIR", BASE_DIR / "data")).expanduser()
DB_PATH = Path(
    os.environ.get("IBS_FIGHTER_DB_PATH", DATA_DIR / "ibs_fighter.sqlite3")
).expanduser()
SCHEMA_PATH = BASE_DIR / "schema.sql"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = Path(os.environ.get("IBS_FIGHTER_UPLOADS_DIR", BASE_DIR / "uploads")).expanduser()

HOST = os.environ.get("IBS_FIGHTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBS_FIGHTER_PORT", "8765"))
AUTH_REQUIRED = os.environ.get("IBS_FIGHTER_AUTH_REQUIRED", "1") not in {"0", "false", "False"}
SECRET_KEY = os.environ.get("SECRET_KEY") or ("" if IS_RENDER else "dev-only-change-me")
SESSION_COOKIE_SECURE = os.environ.get(
    "IBS_FIGHTER_COOKIE_SECURE",
    "1" if IS_RENDER else "0",
) not in {"0", "false", "False"}
SESSION_DAYS = env_int("IBS_FIGHTER_SESSION_DAYS", 360)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_ALLOWED_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("GOOGLE_ALLOWED_EMAILS", "gluebi.d.mao@gmail.com").split(",")
    if email.strip()
}
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_DRIVE_BACKUP_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "")
GOOGLE_DRIVE_OAUTH_TOKEN_PATH = Path(
    os.environ.get("GOOGLE_DRIVE_OAUTH_TOKEN_PATH", DATA_DIR / "google_drive_oauth_token.json")
).expanduser()
BACKUP_ADMIN_TOKEN = os.environ.get("BACKUP_ADMIN_TOKEN", "")
DEFAULT_TIMEZONE = os.environ.get("IBS_FIGHTER_DEFAULT_TIMEZONE", "Pacific/Guadalcanal")
LEGACY_TIMEZONE = os.environ.get("IBS_FIGHTER_LEGACY_TIMEZONE", "Pacific/Port_Moresby")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MEAL_MODEL = os.environ.get("OPENAI_MEAL_MODEL", "gpt-5.4-mini")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
