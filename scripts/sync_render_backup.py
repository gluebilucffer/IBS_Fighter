#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_URL = "https://ibs-fighter.onrender.com"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "render_backups"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def trigger_render_backup(app_url: str, token: str, timeout: int) -> dict:
    if not token:
        raise RuntimeError("缺少 BACKUP_ADMIN_TOKEN，无法触发 Render 备份")

    url = f"{app_url.rstrip('/')}/api/admin/backups/drive"
    request = Request(
        url,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Render 备份请求失败: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Render 备份请求失败: {exc.reason}") from exc


def download_drive_file(file_id: str, file_name: str, download_dir: Path) -> Path | None:
    try:
        from googleapiclient.http import MediaIoBaseDownload

        from ibs_fighter.drive_backup import build_drive_service
    except Exception as exc:
        print(f"跳过 Google Drive API 下载: {exc}", file=sys.stderr)
        return None

    download_dir.mkdir(parents=True, exist_ok=True)
    destination = download_dir / file_name
    try:
        service = build_drive_service()
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        with destination.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return destination
    except Exception as exc:
        print(f"跳过 Google Drive API 下载: {exc}", file=sys.stderr)
        return None


def find_latest_local_backup(folder: Path, expected_name: str | None) -> Path | None:
    if expected_name:
        expected_path = folder / expected_name
        if expected_path.exists():
            return expected_path

    candidates = [path for path in folder.glob("ibs-fighter-backup-*.zip") if path.is_file()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (path.name, path.stat().st_mtime), reverse=True)[0]


def safe_extract(archive: zipfile.ZipFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.infolist():
        destination = (target_dir / member.filename).resolve()
        if not str(destination).startswith(f"{target_root}{os.sep}") and destination != target_root:
            raise RuntimeError(f"备份 zip 包含不安全路径: {member.filename}")
    archive.extractall(target_dir)


def extract_backup(zip_path: Path, output_dir: Path) -> dict:
    if not zip_path.exists():
        raise RuntimeError(f"找不到备份 zip: {zip_path}")

    target_dir = output_dir / zip_path.stem
    db_path = target_dir / "data" / "ibs_fighter.sqlite3"
    manifest_path = target_dir / "manifest.json"

    if not db_path.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            safe_extract(archive, target_dir)

    if not db_path.exists():
        raise RuntimeError(f"备份中没有找到数据库: {db_path}")

    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest_db_path.txt").write_text(f"{db_path}\n", encoding="utf-8")
    (output_dir / "latest_backup_dir.txt").write_text(f"{target_dir}\n", encoding="utf-8")

    return {
        "backup_zip": str(zip_path),
        "backup_dir": str(target_dir),
        "database": str(db_path),
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger the Render Google Drive backup and extract the latest backup locally.",
    )
    parser.add_argument(
        "--app-url",
        default=os.environ.get("IBS_FIGHTER_RENDER_URL", DEFAULT_APP_URL),
        help=f"Render app URL, default: {DEFAULT_APP_URL}",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("BACKUP_ADMIN_TOKEN", ""),
        help="Backup admin token. Defaults to BACKUP_ADMIN_TOKEN from .env or environment.",
    )
    parser.add_argument(
        "--backup-zip",
        type=Path,
        help="Use an already-downloaded backup zip instead of triggering Render.",
    )
    parser.add_argument(
        "--skip-trigger",
        action="store_true",
        help="Do not call Render; import the newest zip from --drive-sync-dir.",
    )
    parser.add_argument(
        "--drive-sync-dir",
        type=Path,
        default=Path(os.environ["GOOGLE_DRIVE_BACKUP_LOCAL_DIR"])
        if os.environ.get("GOOGLE_DRIVE_BACKUP_LOCAL_DIR")
        else None,
        help="Local Google Drive-synced folder containing ibs-fighter-backup-*.zip.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "_downloads",
        help="Where Google Drive API downloads should be saved.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where extracted Render snapshots should be stored.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="Render request timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    load_env_file(REPO_ROOT / ".env")
    args = parse_args()

    backup_zip = args.backup_zip
    backup_payload: dict = {}
    expected_name: str | None = backup_zip.name if backup_zip else None

    if backup_zip is None and not args.skip_trigger:
        backup_payload = trigger_render_backup(args.app_url, args.token, args.timeout)
        backup_info = backup_payload.get("backup") or {}
        expected_name = backup_info.get("file_name")
        file_id = backup_info.get("file_id")
        if file_id and expected_name:
            backup_zip = download_drive_file(file_id, expected_name, args.download_dir)

    if backup_zip is None and args.drive_sync_dir:
        backup_zip = find_latest_local_backup(args.drive_sync_dir.expanduser(), expected_name)

    if backup_zip is None:
        raise RuntimeError(
            "备份已触发但本地没有拿到 zip。请配置 GOOGLE_SERVICE_ACCOUNT_JSON，"
            "或把 Google Drive 备份文件夹同步到本机后传入 --drive-sync-dir。"
        )

    result = extract_backup(backup_zip.expanduser(), args.output_dir.expanduser())
    if backup_payload:
        result["render_backup"] = backup_payload.get("backup", {})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
