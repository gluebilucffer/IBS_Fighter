from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import (
    DB_PATH,
    GOOGLE_DRIVE_BACKUP_FOLDER_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    UPLOADS_DIR,
)


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
APP_PROPERTIES = {
    "app": "ibs-fighter",
    "kind": "sqlite-uploads-backup",
}


def backup_to_google_drive() -> dict:
    if not GOOGLE_DRIVE_BACKUP_FOLDER_ID:
        raise RuntimeError("未配置 GOOGLE_DRIVE_BACKUP_FOLDER_ID")
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("未配置 GOOGLE_SERVICE_ACCOUNT_JSON")
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
    credentials = service_account.Credentials.from_service_account_info(
        load_service_account_info(),
        scopes=[DRIVE_SCOPE],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


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
