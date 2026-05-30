from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import (
    DB_PATH,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_DRIVE_BACKUP_FOLDER_ID,
    GOOGLE_DRIVE_OAUTH_TOKEN_PATH,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    UPLOADS_DIR,
)
from .auth import GOOGLE_TOKEN_URL


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
APP_PROPERTIES = {
    "app": "ibs-fighter",
    "kind": "sqlite-uploads-backup",
}


def backup_to_google_drive() -> dict:
    if not GOOGLE_DRIVE_BACKUP_FOLDER_ID:
        raise RuntimeError("Drive 备份未配置：请在 Render 设置 GOOGLE_DRIVE_BACKUP_FOLDER_ID")
    if not DB_PATH.exists():
        raise RuntimeError(f"数据库文件不存在: {DB_PATH}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"ibs-fighter-backup-{timestamp}.zip"

    with tempfile.TemporaryDirectory(prefix="ibs-fighter-backup-") as tmpdir:
        snapshot_path = Path(tmpdir) / "ibs_fighter.sqlite3"
        snapshot_database(snapshot_path)
        archive_path = Path(tmpdir) / backup_name
        manifest = build_backup_archive(archive_path, snapshot_path, timestamp)
        uploaded = upload_file_to_drive(archive_path, backup_name)

    return {
        "ok": True,
        "backup": {
            "file_name": backup_name,
            "file_id": uploaded["id"],
            "web_view_link": uploaded.get("webViewLink"),
            "size_bytes": manifest["archive_size_bytes"],
            "sha256": manifest["archive_sha256"],
            "created_at": manifest["created_at"],
        },
    }


def drive_backup_status() -> dict:
    error = ""
    try:
        token_info = load_drive_oauth_token()
    except RuntimeError as exc:
        token_info = None
        error = str(exc)
    auth_method = ""
    authorized_email = ""
    if token_info:
        auth_method = "oauth"
        authorized_email = str(token_info.get("email") or "")
    elif GOOGLE_SERVICE_ACCOUNT_JSON:
        auth_method = "service_account"

    return {
        "folder_configured": bool(GOOGLE_DRIVE_BACKUP_FOLDER_ID),
        "google_oauth_configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "authorized": bool(auth_method),
        "auth_method": auth_method,
        "authorized_email": authorized_email,
        "token_path": str(GOOGLE_DRIVE_OAUTH_TOKEN_PATH),
        "error": error,
    }


def store_drive_oauth_token(email: str, token_response: dict) -> dict:
    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Google 没有返回 refresh token，无法保存 Drive 备份授权")

    token_info = {
        "email": email,
        "client_id": GOOGLE_CLIENT_ID,
        "refresh_token": refresh_token,
        "token_uri": GOOGLE_TOKEN_URL,
        "scope": token_response.get("scope") or DRIVE_SCOPE,
        "created_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    }
    GOOGLE_DRIVE_OAUTH_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOOGLE_DRIVE_OAUTH_TOKEN_PATH.write_text(
        json.dumps(token_info, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        GOOGLE_DRIVE_OAUTH_TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return drive_backup_status()


def load_drive_oauth_token() -> dict | None:
    if not GOOGLE_DRIVE_OAUTH_TOKEN_PATH.exists():
        return None
    try:
        token_info = json.loads(GOOGLE_DRIVE_OAUTH_TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google Drive OAuth token 文件无法读取，请重新连接 Drive 备份") from exc
    return token_info if isinstance(token_info, dict) and token_info.get("refresh_token") else None


def snapshot_database(snapshot_path: Path) -> None:
    source_uri = f"file:{DB_PATH}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    try:
        target = sqlite3.connect(snapshot_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def build_backup_archive(archive_path: Path, snapshot_path: Path, timestamp: str) -> dict:
    db_sha256 = sha256_file(snapshot_path)
    uploaded_files = upload_manifest_entries()
    manifest = {
        "created_at": timestamp,
        "database": {
            "path": str(DB_PATH),
            "archive_name": "data/ibs_fighter.sqlite3",
            "size_bytes": snapshot_path.stat().st_size,
            "sha256": db_sha256,
        },
        "uploads": uploaded_files,
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot_path, "data/ibs_fighter.sqlite3")
        if UPLOADS_DIR.exists():
            for file_path in sorted(UPLOADS_DIR.rglob("*")):
                if file_path.is_file():
                    archive.write(file_path, f"uploads/{file_path.relative_to(UPLOADS_DIR)}")
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        )

    manifest["archive_size_bytes"] = archive_path.stat().st_size
    manifest["archive_sha256"] = sha256_file(archive_path)
    return manifest


def upload_manifest_entries() -> list[dict]:
    if not UPLOADS_DIR.exists():
        return []

    entries = []
    for file_path in sorted(UPLOADS_DIR.rglob("*")):
        if not file_path.is_file():
            continue
        entries.append(
            {
                "path": f"uploads/{file_path.relative_to(UPLOADS_DIR)}",
                "size_bytes": file_path.stat().st_size,
                "sha256": sha256_file(file_path),
            }
        )
    return entries


def upload_file_to_drive(path: Path, name: str) -> dict:
    service = build_drive_service()
    media = MediaFileUpload(str(path), mimetype="application/zip", resumable=False)
    metadata = {
        "name": name,
        "parents": [GOOGLE_DRIVE_BACKUP_FOLDER_ID],
        "appProperties": APP_PROPERTIES,
    }
    return (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )


def build_drive_service():
    token_info = load_drive_oauth_token()
    if token_info:
        credentials = build_oauth_credentials(token_info)
    elif GOOGLE_SERVICE_ACCOUNT_JSON:
        credentials = service_account.Credentials.from_service_account_info(
            load_service_account_info(),
            scopes=[DRIVE_SCOPE],
        )
    else:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise RuntimeError("Drive 备份未配置：请在 Render 设置 GOOGLE_CLIENT_ID 和 GOOGLE_CLIENT_SECRET")
        raise RuntimeError("Drive 备份未授权：请在设置页点击“连接 Google Drive 备份”")

    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def build_oauth_credentials(token_info: dict) -> Credentials:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Drive 备份未配置：请在 Render 设置 GOOGLE_CLIENT_ID 和 GOOGLE_CLIENT_SECRET")
    if token_info.get("client_id") and token_info.get("client_id") != GOOGLE_CLIENT_ID:
        raise RuntimeError("Google Drive 授权使用的 OAuth Client 已变化，请重新连接 Drive 备份")

    credentials = Credentials(
        token=None,
        refresh_token=token_info["refresh_token"],
        token_uri=token_info.get("token_uri") or GOOGLE_TOKEN_URL,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=[DRIVE_SCOPE],
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError("Google Drive 授权已失效，请重新连接 Drive 备份") from exc
    return credentials


def load_service_account_info() -> dict:
    raw = GOOGLE_SERVICE_ACCOUNT_JSON.strip()
    if raw.startswith("{"):
        return json.loads(raw)

    possible_path = Path(raw).expanduser()
    if possible_path.exists():
        return json.loads(possible_path.read_text(encoding="utf-8"))

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON 不是 JSON、文件路径或 base64 JSON") from exc
    return json.loads(decoded)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
