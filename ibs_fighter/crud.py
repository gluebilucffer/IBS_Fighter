from __future__ import annotations

import sqlite3

from .db import get_connection
from .models import TABLES, TRACKING_TABLES
from .uploads import save_meal_photo


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
