from __future__ import annotations

import json
import sqlite3
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import DB_PATH, HOST, PORT, STATIC_DIR, UPLOADS_DIR
from .crud import build_day_payload, delete_record, fetch_records, insert_record, update_record
from .db import get_connection, init_database
from .models import TABLES
from .reports import build_report


class IBSFighterHandler(SimpleHTTPRequestHandler):
    server_version = "IBSFighter/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/day":
            query = parse_qs(parsed.query)
            selected_date = query.get("date", [date.today().isoformat()])[0]
            self.send_json(build_day_payload(selected_date))
            return

        if parsed.path == "/api/report":
            query = parse_qs(parsed.query)
            selected_end = query.get("end_date", [date.today().isoformat()])[0]
            module = query.get("module", ["bowel"])[0]
            try:
                days = int(query.get("days", ["7"])[0])
                with get_connection() as conn:
                    self.send_json(build_report(conn, module, selected_end, days))
            except ValueError as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        if parsed.path.startswith("/api/"):
            table = parsed.path.removeprefix("/api/").strip("/")
            if table in TABLES:
                query = parse_qs(parsed.query)
                selected_date = query.get("date", [None])[0]
                self.send_json({"items": fetch_records(table, selected_date)})
                return
            self.send_error_json(HTTPStatus.NOT_FOUND, "未知数据表")
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        table, record_id = self.parse_api_record_path()
        if not table or record_id is not None:
            self.send_error_json(HTTPStatus.NOT_FOUND, "接口不存在")
            return

        try:
            self.send_json(insert_record(table, self.read_json_body()), HTTPStatus.CREATED)
        except (sqlite3.IntegrityError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_PUT(self) -> None:
        self.handle_update()

    def do_PATCH(self) -> None:
        self.handle_update()

    def do_DELETE(self) -> None:
        table, record_id = self.parse_api_record_path()
        if not table or record_id is None:
            self.send_error_json(HTTPStatus.NOT_FOUND, "接口不存在")
            return

        try:
            delete_record(table, record_id)
            self.send_json({"ok": True})
        except sqlite3.IntegrityError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "这条药物已经有用药记录，不能直接删除")
        except LookupError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))

    def handle_update(self) -> None:
        table, record_id = self.parse_api_record_path()
        if not table or record_id is None:
            self.send_error_json(HTTPStatus.NOT_FOUND, "接口不存在")
            return

        try:
            self.send_json(update_record(table, record_id, self.read_json_body()))
        except LookupError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except (sqlite3.IntegrityError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def parse_api_record_path(self) -> tuple[str | None, int | None]:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) not in {2, 3} or parts[0] != "api" or parts[1] not in TABLES:
            return None, None
        if len(parts) == 2:
            return parts[1], None
        try:
            return parts[1], int(parts[2])
        except ValueError:
            return None, None

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("请求体不是有效 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"

        root_dir = UPLOADS_DIR if path.startswith("/uploads/") else STATIC_DIR
        relative_path = path.removeprefix("/uploads/") if root_dir == UPLOADS_DIR else path.removeprefix("/")
        requested = (root_dir / relative_path).resolve()
        if not requested.is_relative_to(root_dir.resolve()) or not requested.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.path = str(requested)
        return super().do_GET()

    def translate_path(self, path: str) -> str:
        return path

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)


def main() -> None:
    init_database()
    server = ThreadingHTTPServer((HOST, PORT), IBSFighterHandler)
    print(f"IBS Fighter running at http://{HOST}:{PORT}")
    if HOST == "0.0.0.0":
        print(f"Local access: http://127.0.0.1:{PORT}")
        print(f"Phone access: http://<your Mac LAN IP>:{PORT}")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()
