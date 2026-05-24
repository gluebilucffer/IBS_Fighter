from __future__ import annotations

import sqlite3

from .config import DB_PATH, SCHEMA_PATH, UPLOADS_DIR
from .timezones import TIME_FIELDS, legacy_utc_for_local


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
    ensure_time_metadata_columns(conn, "bowel_movements")

    meal_columns = {row[1] for row in conn.execute("PRAGMA table_info(meals)").fetchall()}
    if "photo_path" not in meal_columns:
        conn.execute("ALTER TABLE meals ADD COLUMN photo_path TEXT")
    if "photo_filename" not in meal_columns:
        conn.execute("ALTER TABLE meals ADD COLUMN photo_filename TEXT")
    ensure_time_metadata_columns(conn, "meals")

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
    ensure_time_metadata_columns(conn, "medications")
    ensure_time_metadata_columns(conn, "exercises")
    backfill_medication_units(conn)
    drop_sleep_module(conn)


def ensure_time_metadata_columns(conn: sqlite3.Connection, table: str) -> None:
    local_field, timezone_field, utc_field = TIME_FIELDS[table]
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if timezone_field not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {timezone_field} TEXT")
    if utc_field not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {utc_field} TEXT")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{utc_field} ON {table} ({utc_field})")
    backfill_legacy_time_metadata(conn, table, local_field, timezone_field, utc_field)


def backfill_legacy_time_metadata(
    conn: sqlite3.Connection,
    table: str,
    local_field: str,
    timezone_field: str,
    utc_field: str,
) -> None:
    rows = conn.execute(
        f"""
        SELECT id, {local_field} AS local_value
        FROM {table}
        WHERE {local_field} IS NOT NULL
          AND ({timezone_field} IS NULL OR {utc_field} IS NULL)
        """
    ).fetchall()
    for row in rows:
        try:
            timezone_name, utc_value = legacy_utc_for_local(row["local_value"])
        except ValueError:
            continue
        conn.execute(
            f"""
            UPDATE {table}
            SET {timezone_field} = ?, {utc_field} = ?
            WHERE id = ?
            """,
            (timezone_name, utc_value, row["id"]),
        )


def drop_sleep_module(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER IF EXISTS trg_sleep_entries_updated_at")
    conn.execute("DROP INDEX IF EXISTS idx_sleep_entries_sleep_date")
    conn.execute("DROP TABLE IF EXISTS sleep_entries")


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
            taken_timezone TEXT,
            taken_at_utc TEXT,
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
                id, taken_at, taken_timezone, taken_at_utc, product_id, quantity_value, quantity_unit,
                timing_relation, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["taken_at"],
                row["taken_timezone"] if "taken_timezone" in keys else None,
                row["taken_at_utc"] if "taken_at_utc" in keys else None,
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
