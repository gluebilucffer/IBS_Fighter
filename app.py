from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from reports import build_report


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "ibs_fighter.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


TRACKING_TABLES = [
    "bowel_movements",
    "meals",
    "medications",
    "exercises",
    "sleep_entries",
]


TABLES = {
    "bowel_movements": {
        "date_column": "occurred_at",
        "fields": {
            "occurred_at": "text",
            "bristol_type": "int",
            "location": "text",
            "urgency": "int",
            "color": "text",
            "notes": "text",
        },
        "required": {"occurred_at", "bristol_type"},
        "order": "occurred_at ASC, id ASC",
    },
    "meals": {
        "date_column": "eaten_at",
        "fields": {
            "eaten_at": "text",
            "meal_type": "text",
            "location": "text",
            "foods": "text",
            "photo_path": "text",
            "photo_filename": "text",
            "symptoms_after": "text",
            "notes": "text",
        },
        "required": {"eaten_at"},
        "order": "eaten_at ASC, id ASC",
    },
    "medications": {
        "date_column": "taken_at",
        "fields": {
            "taken_at": "text",
            "product_id": "int",
            "quantity_value": "float",
            "quantity_unit": "text",
            "timing_relation": "text",
            "notes": "text",
        },
        "required": {"taken_at", "product_id"},
        "order": "taken_at ASC, id ASC",
    },
    "medication_products": {
        "date_column": None,
        "fields": {
            "product_name": "text",
            "ingredients": "text",
            "product_type": "text",
            "default_unit": "text",
        },
        "required": {"product_name", "product_type", "default_unit"},
        "order": "product_name COLLATE NOCASE ASC, id ASC",
    },
    "exercises": {
        "date_column": "started_at",
        "fields": {
            "started_at": "text",
            "activity_type": "text",
            "duration_minutes": "int",
            "intensity": "text",
            "notes": "text",
        },
        "required": {"started_at", "activity_type"},
        "order": "started_at ASC, id ASC",
    },
    "sleep_entries": {
        "date_column": "sleep_date",
        "fields": {
            "sleep_date": "text",
            "source": "text",
            "started_at": "text",
            "ended_at": "text",
            "duration_minutes": "int",
            "quality": "text",
            "notes": "text",
        },
        "required": {"sleep_date"},
        "order": "sleep_date ASC, id ASC",
    },
}


def init_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrate_database(conn)


def migrate_database(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    bowel_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(bowel_movements)").fetchall()
    }
    if "color" not in bowel_columns:
        conn.execute("ALTER TABLE bowel_movements ADD COLUMN color TEXT")

    meal_columns = {row[1] for row in conn.execute("PRAGMA table_info(meals)").fetchall()}
    if "photo_path" not in meal_columns:
        conn.execute("ALTER TABLE meals ADD COLUMN photo_path TEXT")
    if "photo_filename" not in meal_columns:
        conn.execute("ALTER TABLE meals ADD COLUMN photo_filename TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            ingredients TEXT,
            product_type TEXT NOT NULL,
            default_unit TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(product_name, product_type)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_medication_products_name ON medication_products (product_name)"
    )

    product_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(medication_products)").fetchall()
    }
    if "default_unit" not in product_columns:
        conn.execute(
            "ALTER TABLE medication_products ADD COLUMN default_unit TEXT NOT NULL DEFAULT ''"
        )

    medication_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(medications)").fetchall()
    }
    if "product_id" not in medication_columns or "product_type" in medication_columns:
        rebuild_medications_table(conn)
    backfill_medication_units(conn)


def find_or_create_medication_product(
    conn: sqlite3.Connection,
    product_name: str | None,
    product_type: str | None,
    ingredients: str | None = None,
    default_unit: str | None = None,
) -> int:
    name = (product_name or product_type or "未命名药物").strip()
    med_type = (product_type or "未分类").strip()
    row = conn.execute(
        """
        SELECT id FROM medication_products
        WHERE product_name = ? AND product_type = ?
        """,
        (name, med_type),
    ).fetchone()
    if row:
        return int(row["id"])

    cursor = conn.execute(
        """
        INSERT INTO medication_products (product_name, ingredients, product_type, default_unit)
        VALUES (?, ?, ?, ?)
        """,
        (name, ingredients, med_type, default_unit or ""),
    )
    return int(cursor.lastrowid)


def backfill_medication_units(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE medication_products
        SET default_unit = (
            SELECT medications.quantity_unit
            FROM medications
            WHERE medications.product_id = medication_products.id
              AND medications.quantity_unit IS NOT NULL
              AND medications.quantity_unit != ''
            ORDER BY medications.id DESC
            LIMIT 1
        )
        WHERE default_unit = ''
          AND EXISTS (
            SELECT 1
            FROM medications
            WHERE medications.product_id = medication_products.id
              AND medications.quantity_unit IS NOT NULL
              AND medications.quantity_unit != ''
        )
        """
    )


def rebuild_medications_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER IF EXISTS trg_medications_updated_at")
    conn.execute("ALTER TABLE medications RENAME TO medications_legacy")
    conn.execute(
        """
        CREATE TABLE medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taken_at TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES medication_products(id) ON DELETE RESTRICT,
            quantity_value REAL,
            quantity_unit TEXT,
            timing_relation TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    legacy_rows = conn.execute("SELECT * FROM medications_legacy ORDER BY id ASC").fetchall()
    for row in legacy_rows:
        keys = set(row.keys())
        product_id = row["product_id"] if "product_id" in keys and row["product_id"] else None
        if product_id is None:
            product_id = find_or_create_medication_product(
                conn,
                row["product_name"] if "product_name" in keys else None,
                row["product_type"] if "product_type" in keys else None,
            )

        conn.execute(
            """
            INSERT INTO medications (
                id, taken_at, product_id, quantity_value, quantity_unit,
                timing_relation, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["taken_at"],
                product_id,
                row["quantity_value"] if "quantity_value" in keys else None,
                row["quantity_unit"] if "quantity_unit" in keys else None,
                row["timing_relation"] if "timing_relation" in keys else None,
                row["notes"] if "notes" in keys else None,
                row["created_at"] if "created_at" in keys else None,
                row["updated_at"] if "updated_at" in keys else None,
            ),
        )

    conn.execute("DROP TABLE medications_legacy")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_medications_updated_at
        AFTER UPDATE ON medications
        FOR EACH ROW
        BEGIN
            UPDATE medications SET updated_at = datetime('now') WHERE id = OLD.id;
        END;
        """
    )


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def normalize_payload(table: str, payload: dict, *, partial: bool = False) -> dict:
    config = TABLES[table]
    fields = config["fields"]
    normalized = {}

    missing = config["required"] - set(payload.keys())
    if missing and not partial:
        names = ", ".join(sorted(missing))
        raise ValueError(f"缺少必填字段: {names}")

    for field, field_type in fields.items():
        if field not in payload:
            continue

        value = payload[field]
        if value == "":
            value = None

        if value is None:
            if field in config["required"] and not partial:
                raise ValueError(f"{field} 不能为空")
            normalized[field] = None
            continue

        if field_type == "int":
            try:
                normalized[field] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} 必须是整数") from exc
        elif field_type == "float":
            try:
                normalized[field] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} 必须是数字") from exc
        else:
            normalized[field] = str(value).strip()

    return normalized


def save_meal_photo(payload: dict) -> dict:
    data_url = payload.pop("photo_data_url", None)
    original_name = payload.pop("photo_filename", None)
    if not data_url:
        return {}

    if not isinstance(data_url, str) or "," not in data_url or not data_url.startswith("data:"):
        raise ValueError("照片格式不正确")

    header, encoded = data_url.split(",", 1)
    mime_type = header.removeprefix("data:").split(";", 1)[0].lower()
    extension = IMAGE_EXTENSIONS.get(mime_type)
    if extension is None:
        raise ValueError("照片只支持 JPG、PNG、WEBP 或 GIF")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError("照片内容无法读取") from exc

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("照片不能超过 10MB")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}-{uuid4().hex}{extension}"
    target = UPLOADS_DIR / filename
    target.write_bytes(image_bytes)

    return {
        "photo_path": f"/uploads/{filename}",
        "photo_filename": str(original_name).strip() if original_name else filename,
    }


def record_columns(table: str) -> list[str]:
    return ["id", *TABLES[table]["fields"].keys(), "created_at", "updated_at"]


def fetch_record_by_id(conn: sqlite3.Connection, table: str, record_id: int) -> sqlite3.Row:
    if table == "medications":
        return conn.execute(medications_select_sql("WHERE medications.id = ?"), (record_id,)).fetchone()
    columns = ", ".join(record_columns(table))
    return conn.execute(f"SELECT {columns} FROM {table} WHERE id = ?", (record_id,)).fetchone()


def medications_select_sql(where_sql: str = "") -> str:
    return f"""
        SELECT
            medications.id,
            medications.taken_at,
            medications.product_id,
            medications.quantity_value,
            medications.quantity_unit,
            medications.timing_relation,
            medications.notes,
            medications.created_at,
            medications.updated_at,
            medication_products.product_name,
            medication_products.product_type,
            medication_products.default_unit,
            medication_products.ingredients
        FROM medications
        LEFT JOIN medication_products ON medication_products.id = medications.product_id
        {where_sql}
    """


def fetch_records(table: str, selected_date: str | None = None) -> list[dict]:
    config = TABLES[table]
    if table == "medications":
        params: list[str] = []
        where_sql = ""
        if selected_date:
            where_sql = "WHERE date(medications.taken_at) = ?"
            params.append(selected_date)
        sql = medications_select_sql(where_sql) + " ORDER BY medications.taken_at ASC, medications.id ASC"
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(row) for row in rows]

    sql = f"SELECT {', '.join(record_columns(table))} FROM {table}"
    params: list[str] = []
    if selected_date and config["date_column"]:
        date_column = config["date_column"]
        if date_column == "sleep_date":
            sql += f" WHERE {date_column} = ?"
        else:
            sql += f" WHERE date({date_column}) = ?"
        params.append(selected_date)
    sql += f" ORDER BY {config['order']}"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def insert_record(table: str, payload: dict) -> dict:
    payload = dict(payload)
    extra_data = save_meal_photo(payload) if table == "meals" else {}
    data = normalize_payload(table, payload)
    if table == "meals" and data.get("foods") is None:
        data["foods"] = ""
    data.update(extra_data)
    columns = list(data.keys())
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)

    with get_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
            [data[column] for column in columns],
        )
        row = fetch_record_by_id(conn, table, cursor.lastrowid)
    return row_to_dict(row)


def update_record(table: str, record_id: int, payload: dict) -> dict:
    payload = dict(payload)
    extra_data = save_meal_photo(payload) if table == "meals" else {}
    data = normalize_payload(table, payload, partial=True)
    if table == "meals" and data.get("foods") is None:
        data["foods"] = ""
    data.update(extra_data)
    if not data:
        raise ValueError("没有可更新字段")

    assignments = ", ".join(f"{column} = ?" for column in data)
    values = [data[column] for column in data]
    values.append(record_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", values)
        if cursor.rowcount == 0:
            raise LookupError("记录不存在")
        row = fetch_record_by_id(conn, table, record_id)
    return row_to_dict(row)


def delete_record(table: str, record_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            raise LookupError("记录不存在")


def build_day_payload(selected_date: str) -> dict:
    records = {table: fetch_records(table, selected_date) for table in TRACKING_TABLES}
    bristol_values = [
        item["bristol_type"]
        for item in records["bowel_movements"]
        if item.get("bristol_type") is not None
    ]
    exercise_minutes = sum(item.get("duration_minutes") or 0 for item in records["exercises"])

    avg_bristol = None
    if bristol_values:
        avg_bristol = round(sum(bristol_values) / len(bristol_values), 1)

    return {
        "date": selected_date,
        "summary": {
            "bowel_events": len(records["bowel_movements"]),
            "avg_bristol": avg_bristol,
            "meals": len(records["meals"]),
            "medications": len(records["medications"]),
            "exercise_minutes": exercise_minutes,
            "sleep_minutes": sum(item.get("duration_minutes") or 0 for item in records["sleep_entries"]),
        },
        "records": records,
        "medication_products": fetch_records("medication_products"),
        "meal_locations": fetch_meal_locations(),
    }


def fetch_meal_locations() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT location
            FROM meals
            WHERE location IS NOT NULL AND location != ''
            ORDER BY location COLLATE NOCASE ASC
            """
        ).fetchall()
    return [row["location"] for row in rows]


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
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), IBSFighterHandler)
    print(f"IBS Fighter running at http://{host}:{port}")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
