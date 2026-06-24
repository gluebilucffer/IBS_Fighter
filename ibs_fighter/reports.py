from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from math import sqrt


REPORT_TRACKING_START_DATE = date(2026, 5, 12)
BRISTOL_SAFE_LEVELS = {4, 5}

BRISTOL_LABELS = {
    1: "1 硬球状",
    2: "2 结块香肠状",
    3: "3 表面裂纹",
    4: "4 光滑柔软",
    5: "5 软块",
    6: "6 糊状",
    7: "7 水样",
}

QUALITY_BUCKETS = {
    "below": {"label": "低于安全区", "levels": {1, 2, 3}},
    "safe": {"label": "安全区", "levels": BRISTOL_SAFE_LEVELS},
    "above": {"label": "高于安全区", "levels": {6, 7}},
}


def build_report(
    conn: sqlite3.Connection,
    module: str,
    end_date_text: str | None,
    days: int,
) -> dict:
    if module == "weight":
        return build_weight_report(conn, end_date_text, days)
    if module == "medications":
        return build_medication_report(conn, end_date_text, days)
    return build_bowel_report(conn, end_date_text, days)


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def safe_average(values: list[float | int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def safe_rate(part: int, whole: int) -> float:
    if whole == 0:
        return 0
    return round(part / whole * 100, 1)


def rounded_float(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 1)


def report_range(
    end_date_text: str | None,
    days: int,
) -> tuple[int, int, date, date, list[str], bool]:
    if days not in {7, 30}:
        days = 7

    try:
        end = date.fromisoformat(end_date_text or date.today().isoformat())
    except ValueError as exc:
        raise ValueError("报表日期格式不正确") from exc

    requested_days = days
    requested_start = end - timedelta(days=requested_days - 1)
    start = max(requested_start, REPORT_TRACKING_START_DATE)
    if end < REPORT_TRACKING_START_DATE:
        date_keys: list[str] = []
    else:
        effective_days = (end - start).days + 1
        date_keys = [
            (start + timedelta(days=index)).isoformat()
            for index in range(effective_days)
        ]
    return requested_days, len(date_keys), start, end, date_keys, start != requested_start


def build_bowel_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    requested_days, effective_days, start, end, date_keys, clamped = report_range(
        end_date_text,
        days,
    )
    rows = fetch_bowel_rows(conn, start.isoformat(), end.isoformat())
    return build_bowel_report_from_rows(
        rows,
        date_keys,
        requested_days,
        effective_days,
        start.isoformat(),
        end.isoformat(),
        clamped,
    )


def build_medication_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    requested_days, effective_days, start, end, date_keys, clamped = report_range(
        end_date_text,
        days,
    )
    rows = fetch_medication_rows(conn, start.isoformat(), end.isoformat())
    return build_medication_report_from_rows(
        rows,
        date_keys,
        requested_days,
        effective_days,
        start.isoformat(),
        end.isoformat(),
        clamped,
    )


def build_weight_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    requested_days, effective_days, start, end, date_keys, clamped = report_range(
        end_date_text,
        days,
    )
    rows = fetch_weight_rows(conn, start.isoformat(), end.isoformat())
    return build_weight_report_from_rows(
        rows,
        date_keys,
        requested_days,
        effective_days,
        start.isoformat(),
        end.isoformat(),
        clamped,
    )


def fetch_bowel_rows(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            id,
            occurred_at,
            bristol_type,
            location,
            urgency,
            color,
            notes,
            created_at,
            updated_at
        FROM bowel_movements
        WHERE date(occurred_at) BETWEEN ? AND ?
        ORDER BY occurred_at ASC, id ASC
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def fetch_medication_rows(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict]:
    rows = conn.execute(
        """
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
        WHERE date(medications.taken_at) BETWEEN ? AND ?
        ORDER BY medications.taken_at ASC, medications.id ASC
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def fetch_weight_rows(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            id,
            measured_at,
            weight_kg,
            measurement_context,
            notes,
            created_at,
            updated_at
        FROM body_weights
        WHERE date(measured_at) BETWEEN ? AND ?
        ORDER BY measured_at ASC, id ASC
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def build_bowel_report_from_rows(
    rows: list[dict],
    date_keys: list[str],
    requested_days: int,
    effective_days: int,
    start_date: str,
    end_date: str,
    clamped_to_tracking_start: bool,
) -> dict:
    daily = {
        day: {
            "date": day,
            "count": 0,
            "avg_bristol": None,
            "abnormal_count": 0,
            "below_count": 0,
            "safe_count": 0,
            "above_count": 0,
            "urgent_count": 0,
            "colors": {},
            "locations": {},
            "_bristol_values": [],
        }
        for day in date_keys
    }
    bristol_counts = {level: 0 for level in range(1, 8)}
    quality_counts = {
        key: {"label": config["label"], "count": 0}
        for key, config in QUALITY_BUCKETS.items()
    }
    color_counts: dict[str, dict] = {}
    location_counts: dict[str, dict] = {}
    bristol_values: list[int] = []
    control_points: list[dict] = []

    for item in rows:
        day = (item.get("occurred_at") or "")[:10]
        if day not in daily:
            continue

        bristol = int(item["bristol_type"]) if item.get("bristol_type") is not None else None
        urgency = int(item["urgency"]) if item.get("urgency") is not None else None
        color = item.get("color") or "未记录颜色"
        location = item.get("location") or "未记录地点"
        day_row = daily[day]
        day_row["count"] += 1
        day_row["colors"][color] = day_row["colors"].get(color, 0) + 1
        day_row["locations"][location] = day_row["locations"].get(location, 0) + 1
        increment_rank(color_counts, color)
        increment_rank(location_counts, location)

        if bristol is not None:
            bristol_values.append(bristol)
            day_row["_bristol_values"].append(bristol)
            bristol_counts[bristol] += 1
            bucket = bristol_quality_bucket(bristol)
            quality_counts[bucket]["count"] += 1
            day_row[f"{bucket}_count"] += 1
            if bucket != "safe":
                day_row["abnormal_count"] += 1
            control_points.append(build_control_point(item, len(control_points) + 1, bristol))

        if urgency is not None and urgency >= 3:
            day_row["urgent_count"] += 1

    daily_rows = []
    for day in date_keys:
        row = daily[day]
        row["avg_bristol"] = safe_average(row["_bristol_values"])
        row["dominant_color"] = top_label(row["colors"])
        row["dominant_location"] = top_label(row["locations"])
        row.pop("_bristol_values")
        daily_rows.append(row)

    total_events = len(rows)
    safe_count = quality_counts["safe"]["count"]
    abnormal_count = total_events - safe_count
    urgent_count = sum(row["urgent_count"] for row in daily_rows)
    days_with_records = sum(1 for row in daily_rows if row["count"] > 0)
    no_record_days = [row["date"] for row in daily_rows if row["count"] == 0]
    frequent_days = [row for row in daily_rows if row["count"] >= 3]
    attention_days = [
        build_attention_day(row)
        for row in daily_rows
        if row["abnormal_count"] > 0 or row["urgent_count"] > 0 or row["count"] >= 3
    ]

    return {
        "module": "bowel",
        "range": {
            "days": effective_days,
            "requested_days": requested_days,
            "start_date": start_date,
            "end_date": end_date,
            "dates": date_keys,
            "tracking_start_date": REPORT_TRACKING_START_DATE.isoformat(),
            "clamped_to_tracking_start": clamped_to_tracking_start,
        },
        "summary": {
            "total_events": total_events,
            "days_with_records": days_with_records,
            "no_record_days": len(no_record_days),
            "avg_events_per_day": safe_average([row["count"] for row in daily_rows]),
            "avg_events_per_recorded_day": safe_average(
                [row["count"] for row in daily_rows if row["count"] > 0]
            ),
            "avg_bristol": safe_average(bristol_values),
            "safe_count": safe_count,
            "safe_rate": safe_rate(safe_count, total_events),
            "normal_rate": safe_rate(safe_count, total_events),
            "abnormal_count": abnormal_count,
            "abnormal_rate": safe_rate(abnormal_count, total_events),
            "urgent_count": urgent_count,
            "frequent_days": len(frequent_days),
        },
        "daily": daily_rows,
        "bristol_distribution": [
            {
                "type": level,
                "label": BRISTOL_LABELS[level],
                "count": bristol_counts[level],
                "rate": safe_rate(bristol_counts[level], total_events),
            }
            for level in range(1, 8)
        ],
        "quality_distribution": list(quality_counts.values()),
        "color_distribution": sorted_rank_rows(color_counts, "count"),
        "location_distribution": sorted_rank_rows(location_counts, "count"),
        "control_limits": {
            "min": 1,
            "max": 7,
            "safe_min": min(BRISTOL_SAFE_LEVELS),
            "safe_max": max(BRISTOL_SAFE_LEVELS),
        },
        "control_points": control_points,
        "safety_p_chart": build_safety_p_chart(daily_rows, safe_count, total_events),
        "unsafe_interval_g_chart": build_unsafe_interval_g_chart(rows, end_date),
        "attention_days": attention_days,
        "no_record_dates": no_record_days,
        "insights": build_bowel_insights(
            total_events=total_events,
            avg_bristol=safe_average(bristol_values),
            abnormal_rate=safe_rate(abnormal_count, total_events),
            urgent_count=urgent_count,
            frequent_days=len(frequent_days),
            no_record_days=len(no_record_days),
            days=effective_days,
        ),
    }


def build_weight_report_from_rows(
    rows: list[dict],
    date_keys: list[str],
    requested_days: int,
    effective_days: int,
    start_date: str,
    end_date: str,
    clamped_to_tracking_start: bool,
) -> dict:
    daily = {
        day: {
            "date": day,
            "count": 0,
            "measured_at": None,
            "weight_kg": None,
            "measurement_context": None,
            "notes": None,
        }
        for day in date_keys
    }

    for item in rows:
        day = (item.get("measured_at") or "")[:10]
        if day not in daily:
            continue

        day_row = daily[day]
        day_row["count"] += 1
        day_row["measured_at"] = item.get("measured_at")
        day_row["weight_kg"] = rounded_float(item.get("weight_kg"))
        day_row["measurement_context"] = item.get("measurement_context")
        day_row["notes"] = item.get("notes")

    daily_rows = [daily[day] for day in date_keys]
    trend_points = []
    previous_point = None
    for row in daily_rows:
        if row["weight_kg"] is None:
            continue

        point = {
            "date": row["date"],
            "measured_at": row["measured_at"],
            "weight_kg": row["weight_kg"],
            "measurement_context": row["measurement_context"],
            "record_count": row["count"],
            "change_from_previous_kg": None,
        }
        if previous_point:
            point["change_from_previous_kg"] = rounded_float(
                point["weight_kg"] - previous_point["weight_kg"]
            )
        trend_points.append(point)
        previous_point = point

    no_record_days = [row["date"] for row in daily_rows if row["count"] == 0]
    days_with_records = len(trend_points)
    weight_values = [point["weight_kg"] for point in trend_points]
    first_point = trend_points[0] if trend_points else None
    latest_point = trend_points[-1] if trend_points else None
    min_point = min(trend_points, key=lambda point: point["weight_kg"]) if trend_points else None
    max_point = max(trend_points, key=lambda point: point["weight_kg"]) if trend_points else None
    change_kg = (
        rounded_float(latest_point["weight_kg"] - first_point["weight_kg"])
        if first_point and latest_point and first_point is not latest_point
        else None
    )

    return {
        "module": "weight",
        "range": {
            "days": effective_days,
            "requested_days": requested_days,
            "start_date": start_date,
            "end_date": end_date,
            "dates": date_keys,
            "tracking_start_date": REPORT_TRACKING_START_DATE.isoformat(),
            "clamped_to_tracking_start": clamped_to_tracking_start,
        },
        "summary": {
            "total_records": len(rows),
            "days_with_records": days_with_records,
            "no_record_days": len(no_record_days),
            "coverage_rate": safe_rate(days_with_records, effective_days),
            "latest_weight_kg": latest_point["weight_kg"] if latest_point else None,
            "latest_date": latest_point["date"] if latest_point else None,
            "first_weight_kg": first_point["weight_kg"] if first_point else None,
            "first_date": first_point["date"] if first_point else None,
            "change_kg": change_kg,
            "avg_weight_kg": safe_average(weight_values),
            "min_weight_kg": min_point["weight_kg"] if min_point else None,
            "min_weight_date": min_point["date"] if min_point else None,
            "max_weight_kg": max_point["weight_kg"] if max_point else None,
            "max_weight_date": max_point["date"] if max_point else None,
        },
        "daily": daily_rows,
        "trend_points": trend_points,
        "attention_days": build_weight_attention_days(trend_points),
        "no_record_dates": no_record_days,
        "insights": build_weight_insights(
            total_records=len(rows),
            days_with_records=days_with_records,
            change_kg=change_kg,
            coverage_rate=safe_rate(days_with_records, effective_days),
            no_record_days=len(no_record_days),
            days=effective_days,
        ),
    }


def build_medication_report_from_rows(
    rows: list[dict],
    date_keys: list[str],
    requested_days: int,
    effective_days: int,
    start_date: str,
    end_date: str,
    clamped_to_tracking_start: bool,
) -> dict:
    daily = {
        day: {
            "date": day,
            "count": 0,
            "products": {},
            "types": {},
            "timing_relations": {},
            "dominant_product": None,
            "dominant_type": None,
            "dominant_timing_relation": None,
        }
        for day in date_keys
    }
    product_usage: dict[str, dict] = {}
    type_counts: dict[str, dict] = {}
    timing_counts: dict[str, dict] = {}

    for item in rows:
        day = (item.get("taken_at") or "")[:10]
        if day not in daily:
            continue

        product_name = item.get("product_name") or "未登记药物"
        product_type = item.get("product_type") or "未分类"
        timing_relation = item.get("timing_relation") or "未记录关系"
        quantity_value = item.get("quantity_value") or 0
        unit = item.get("quantity_unit") or item.get("default_unit") or ""
        product_key = str(item.get("product_id") or product_name)
        day_row = daily[day]

        day_row["count"] += 1
        day_row["products"][product_name] = day_row["products"].get(product_name, 0) + 1
        day_row["types"][product_type] = day_row["types"].get(product_type, 0) + 1
        day_row["timing_relations"][timing_relation] = (
            day_row["timing_relations"].get(timing_relation, 0) + 1
        )

        if product_key not in product_usage:
            product_usage[product_key] = {
                "label": product_name,
                "type": product_type,
                "count": 0,
                "quantity": 0,
                "unit": unit,
                "active_days": set(),
            }
        product_usage[product_key]["count"] += 1
        product_usage[product_key]["quantity"] += quantity_value
        product_usage[product_key]["active_days"].add(day)

        increment_rank(type_counts, product_type)
        increment_rank(timing_counts, timing_relation)

    daily_rows = []
    for day in date_keys:
        row = daily[day]
        row["dominant_product"] = top_label(row["products"])
        row["dominant_type"] = top_label(row["types"])
        row["dominant_timing_relation"] = top_label(row["timing_relations"])
        daily_rows.append(row)

    product_rows = []
    for row in product_usage.values():
        product_rows.append(
            {
                "label": row["label"],
                "type": row["type"],
                "count": row["count"],
                "quantity": round(row["quantity"], 2),
                "unit": row["unit"],
                "active_days": len(row["active_days"]),
            }
        )
    product_rows = sorted_rank_rows(
        {f"{row['label']}|{row['type']}": row for row in product_rows},
        "count",
    )

    total_records = len(rows)
    days_with_records = sum(1 for row in daily_rows if row["count"] > 0)
    no_record_days = [row["date"] for row in daily_rows if row["count"] == 0]
    high_load_days = [row for row in daily_rows if row["count"] >= 4]
    type_rows = sorted_rank_rows(type_counts, "count")
    timing_rows = sorted_rank_rows(timing_counts, "count")

    return {
        "module": "medications",
        "range": {
            "days": effective_days,
            "requested_days": requested_days,
            "start_date": start_date,
            "end_date": end_date,
            "dates": date_keys,
            "tracking_start_date": REPORT_TRACKING_START_DATE.isoformat(),
            "clamped_to_tracking_start": clamped_to_tracking_start,
        },
        "summary": {
            "total_records": total_records,
            "days_with_records": days_with_records,
            "no_record_days": len(no_record_days),
            "active_products": len(product_rows),
            "active_types": len(type_rows),
            "avg_records_per_day": safe_average([row["count"] for row in daily_rows]),
            "avg_records_per_recorded_day": safe_average(
                [row["count"] for row in daily_rows if row["count"] > 0]
            ),
            "high_load_days": len(high_load_days),
            "top_product": product_rows[0] if product_rows else None,
            "top_type": type_rows[0] if type_rows else None,
            "top_timing_relation": timing_rows[0] if timing_rows else None,
        },
        "daily": daily_rows,
        "product_usage": product_rows,
        "type_distribution": type_rows,
        "timing_distribution": timing_rows,
        "high_load_days": [
            {
                "date": row["date"],
                "count": row["count"],
                "dominant_product": row["dominant_product"],
                "dominant_type": row["dominant_type"],
                "dominant_timing_relation": row["dominant_timing_relation"],
            }
            for row in high_load_days
        ],
        "no_record_dates": no_record_days,
        "insights": build_medication_insights(
            total_records=total_records,
            active_products=len(product_rows),
            top_product=product_rows[0] if product_rows else None,
            top_type=type_rows[0] if type_rows else None,
            top_timing_relation=timing_rows[0] if timing_rows else None,
            high_load_days=len(high_load_days),
            no_record_days=len(no_record_days),
            days=effective_days,
        ),
    }


def build_weight_attention_days(points: list[dict]) -> list[dict]:
    attention = []
    for point in points:
        change = point.get("change_from_previous_kg")
        if change is None or abs(change) < 1:
            continue
        attention.append(
            {
                "date": point["date"],
                "weight_kg": point["weight_kg"],
                "measurement_context": point.get("measurement_context"),
                "change_from_previous_kg": change,
                "reasons": [f"较上次记录变化 {change:+.1f} kg"],
            }
        )
    return attention


def bristol_quality_bucket(bristol_type: int) -> str:
    for key, config in QUALITY_BUCKETS.items():
        if bristol_type in config["levels"]:
            return key
    return "safe"


def is_bristol_safe(bristol_type: int) -> bool:
    return bristol_type in BRISTOL_SAFE_LEVELS


def build_control_point(item: dict, index: int, bristol_type: int) -> dict:
    is_safe = is_bristol_safe(bristol_type)
    if is_safe:
        status = "safe"
    elif bristol_type < min(BRISTOL_SAFE_LEVELS):
        status = "below"
    else:
        status = "above"

    return {
        "index": index,
        "date": (item.get("occurred_at") or "")[:10],
        "occurred_at": item.get("occurred_at"),
        "bristol_type": bristol_type,
        "label": BRISTOL_LABELS.get(bristol_type, str(bristol_type)),
        "is_safe": is_safe,
        "status": status,
        "urgency": item.get("urgency"),
        "location": item.get("location") or "",
        "color": item.get("color") or "",
    }


def parse_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def build_safety_p_chart(
    daily_rows: list[dict],
    safe_count: int,
    total_events: int,
) -> dict:
    p_bar = safe_count / total_events if total_events else None
    points = []
    for row in daily_rows:
        count = row["count"]
        if count == 0:
            points.append(
                {
                    "date": row["date"],
                    "count": 0,
                    "safe_count": 0,
                    "unsafe_count": 0,
                    "safe_rate": None,
                    "centerline": safe_rate(safe_count, total_events),
                    "lcl": None,
                    "ucl": None,
                    "status": "no_data",
                }
            )
            continue

        row_safe_count = row["safe_count"]
        row_safe_rate = row_safe_count / count
        lcl = None
        ucl = None
        status = "stable"
        if p_bar is not None:
            sigma = sqrt(p_bar * (1 - p_bar) / count)
            lcl = max(0, p_bar - 3 * sigma)
            ucl = min(1, p_bar + 3 * sigma)
            if row_safe_rate < lcl or row_safe_rate > ucl:
                status = "special_cause"
            elif row["abnormal_count"] > 0:
                status = "has_unsafe"

        points.append(
            {
                "date": row["date"],
                "count": count,
                "safe_count": row_safe_count,
                "unsafe_count": row["abnormal_count"],
                "safe_rate": round(row_safe_rate * 100, 1),
                "centerline": safe_rate(safe_count, total_events),
                "lcl": round(lcl * 100, 1) if lcl is not None else None,
                "ucl": round(ucl * 100, 1) if ucl is not None else None,
                "status": status,
            }
        )

    return {
        "overall_safe_rate": safe_rate(safe_count, total_events),
        "safe_count": safe_count,
        "total_events": total_events,
        "days_with_records": sum(1 for row in daily_rows if row["count"] > 0),
        "points": points,
    }


def build_unsafe_interval_g_chart(rows: list[dict], end_date: str) -> dict:
    unsafe_points = []
    all_events = []
    for index, item in enumerate(rows):
        bristol = int(item["bristol_type"]) if item.get("bristol_type") is not None else None
        occurred_at = parse_local_datetime(item.get("occurred_at"))
        event = {
            "index": index,
            "id": item["id"],
            "date": (item.get("occurred_at") or "")[:10],
            "occurred_at": item.get("occurred_at"),
            "occurred_datetime": occurred_at,
            "bristol_type": bristol,
            "is_safe": bristol is not None and is_bristol_safe(bristol),
        }
        all_events.append(event)
        if bristol is not None and not is_bristol_safe(bristol):
            unsafe_points.append(event)

    points = []
    previous_unsafe = None
    for unsafe in unsafe_points:
        if previous_unsafe is None:
            days_since = None
            safe_events_between = None
            bowel_events_between = None
        else:
            days_since = days_between(previous_unsafe, unsafe)
            bowel_events_between = unsafe["index"] - previous_unsafe["index"] - 1
            safe_events_between = sum(
                1
                for event in all_events[previous_unsafe["index"] + 1:unsafe["index"]]
                if event["is_safe"]
            )
        points.append(
            {
                "date": unsafe["date"],
                "occurred_at": unsafe["occurred_at"],
                "bristol_type": unsafe["bristol_type"],
                "days_since_previous_unsafe": days_since,
                "safe_events_since_previous_unsafe": safe_events_between,
                "bowel_events_since_previous_unsafe": bowel_events_between,
            }
        )
        previous_unsafe = unsafe

    latest_unsafe = unsafe_points[-1] if unsafe_points else None
    current_safe_events = None
    current_days = None
    if latest_unsafe is not None:
        current_safe_events = sum(
            1
            for event in all_events[latest_unsafe["index"] + 1:]
            if event["is_safe"]
        )
        current_days = days_from_event_to_date(latest_unsafe, end_date)
    elif all_events:
        current_safe_events = sum(1 for event in all_events if event["is_safe"])

    interval_values = [
        point["safe_events_since_previous_unsafe"]
        for point in points
        if point["safe_events_since_previous_unsafe"] is not None
    ]

    return {
        "unsafe_count": len(unsafe_points),
        "total_events": len(all_events),
        "current_safe_events_after_last_unsafe": current_safe_events,
        "current_days_after_last_unsafe": current_days,
        "longest_safe_events_between_unsafe": max(interval_values) if interval_values else None,
        "points": points,
    }


def days_between(previous: dict, current: dict) -> int | None:
    previous_at = previous.get("occurred_datetime")
    current_at = current.get("occurred_datetime")
    if previous_at is None or current_at is None:
        return None
    return (current_at.date() - previous_at.date()).days


def days_from_event_to_date(event: dict, end_date: str) -> int | None:
    occurred_at = event.get("occurred_datetime")
    if occurred_at is None:
        return None
    try:
        end = date.fromisoformat(end_date)
    except ValueError:
        return None
    return (end - occurred_at.date()).days


def increment_rank(rows: dict[str, dict], label: str) -> None:
    rows.setdefault(label, {"label": label, "count": 0})["count"] += 1


def sorted_rank_rows(rows: dict[str, dict], value_key: str) -> list[dict]:
    return sorted(rows.values(), key=lambda row: (-row[value_key], row.get("label", "")))


def top_label(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def build_attention_day(row: dict) -> dict:
    reasons = []
    if row["below_count"]:
        reasons.append(f"低于安全区 {row['below_count']} 次")
    if row["above_count"]:
        reasons.append(f"高于安全区 {row['above_count']} 次")
    if row["urgent_count"]:
        reasons.append(f"急迫 {row['urgent_count']} 次")
    if row["count"] >= 3:
        reasons.append("一天 3 次以上")

    return {
        "date": row["date"],
        "count": row["count"],
        "avg_bristol": row["avg_bristol"],
        "reasons": reasons,
        "dominant_color": row["dominant_color"],
        "dominant_location": row["dominant_location"],
    }


def build_bowel_insights(
    *,
    total_events: int,
    avg_bristol: float | None,
    abnormal_rate: float,
    urgent_count: int,
    frequent_days: int,
    no_record_days: int,
    days: int,
) -> list[str]:
    if total_events == 0:
        return ["这个周期没有排便记录，报表暂时无法判断趋势。"]

    insights = []
    if avg_bristol is not None:
        if avg_bristol >= 5.5:
            insights.append("平均等级高于安全区，后续可以重点对照饮食、用药和急迫感。")
        elif avg_bristol < 4:
            insights.append("平均等级低于安全区，后续可以留意无排便日、饮水和运动。")
        else:
            insights.append("平均布里斯托等级接近 4-5 安全区，重点看控制图里的越界点。")

    if abnormal_rate >= 30:
        insights.append(f"非安全值占 {abnormal_rate}%，建议优先查看控制图标记日期前后的饮食和用药。")

    if urgent_count:
        insights.append(f"有 {urgent_count} 次急迫感较高的记录，可以作为 IBS 触发因素分析的重点样本。")

    if frequent_days:
        insights.append(f"有 {frequent_days} 天排便次数达到 3 次或更多，适合单独回看当天饮食。")

    if no_record_days >= max(2, round(days * 0.25)):
        insights.append(f"有 {no_record_days} 天没有排便记录，需要区分是未记录还是确实没有排便。")

    return insights


def build_medication_insights(
    *,
    total_records: int,
    active_products: int,
    top_product: dict | None,
    top_type: dict | None,
    top_timing_relation: dict | None,
    high_load_days: int,
    no_record_days: int,
    days: int,
) -> list[str]:
    if total_records == 0:
        return ["这个周期没有用药记录，报表暂时无法判断使用模式。"]

    insights = [
        f"这个周期记录了 {total_records} 条用药，涉及 {active_products} 种药物。"
    ]
    if top_product:
        insights.append(
            f"最常记录的是 {top_product['label']}，共 {top_product['count']} 次。"
        )
    if top_type:
        insights.append(f"主要类型是 {top_type['label']}，共 {top_type['count']} 次。")
    if top_timing_relation:
        insights.append(
            f"最常见服用时间关系是 {top_timing_relation['label']}，共 {top_timing_relation['count']} 次。"
        )
    if high_load_days:
        insights.append(f"有 {high_load_days} 天记录了 4 种或更多用药，适合和当天症状一起回看。")
    if no_record_days >= max(2, round(days * 0.25)):
        insights.append(f"有 {no_record_days} 天没有用药记录，需要区分是未服用还是忘记记录。")

    return insights


def build_weight_insights(
    *,
    total_records: int,
    days_with_records: int,
    change_kg: float | None,
    coverage_rate: float,
    no_record_days: int,
    days: int,
) -> list[str]:
    if total_records == 0:
        return ["这个周期没有体重记录，先固定同一时间和同一条件记录，之后再看趋势。"]

    insights = [
        f"这个周期有 {days_with_records} 天体重数据，记录覆盖率 {coverage_rate}%。"
    ]
    if change_kg is not None:
        if change_kg <= -2:
            insights.append(
                f"周期内体重下降 {abs(change_kg):.1f} kg；如果不是主动减重，建议和饮食摄入、腹泻频率、用药变化一起回看。"
            )
        elif change_kg >= 2:
            insights.append(
                f"周期内体重上升 {change_kg:.1f} kg；建议确认是否与测量时间、盐分摄入、运动或便秘积累有关。"
            )
        elif abs(change_kg) < 1:
            insights.append("周期内体重变化小于 1 kg，更适合看周均趋势，不要被单日波动带偏。")
        else:
            insights.append(f"周期内体重变化 {change_kg:+.1f} kg，建议继续按同一条件记录。")

    if no_record_days >= max(2, round(days * 0.4)):
        insights.append(
            f"有 {no_record_days} 天没有体重记录；体重监控最好保持固定频率，否则很难判断真实趋势。"
        )

    insights.append("后续分析时，把体重变化日期和排便、饮食、用药模块按 3-7 天窗口一起看。")
    return insights
