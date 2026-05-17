from __future__ import annotations

import sqlite3
from datetime import date, timedelta


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
    "hard": {"label": "偏硬", "levels": {1, 2}},
    "normal": {"label": "相对正常", "levels": {3, 4, 5}},
    "loose": {"label": "偏稀", "levels": {6, 7}},
}


def build_report(
    conn: sqlite3.Connection,
    module: str,
    end_date_text: str | None,
    days: int,
) -> dict:
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


def report_range(end_date_text: str | None, days: int) -> tuple[int, date, date, list[str]]:
    if days not in {7, 30}:
        days = 7

    try:
        end = date.fromisoformat(end_date_text or date.today().isoformat())
    except ValueError as exc:
        raise ValueError("报表日期格式不正确") from exc

    start = end - timedelta(days=days - 1)
    date_keys = [(start + timedelta(days=index)).isoformat() for index in range(days)]
    return days, start, end, date_keys


def build_bowel_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    days, start, end, date_keys = report_range(end_date_text, days)
    rows = fetch_bowel_rows(conn, start.isoformat(), end.isoformat())
    return build_bowel_report_from_rows(rows, date_keys, days, start.isoformat(), end.isoformat())


def build_medication_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    days, start, end, date_keys = report_range(end_date_text, days)
    rows = fetch_medication_rows(conn, start.isoformat(), end.isoformat())
    return build_medication_report_from_rows(
        rows,
        date_keys,
        days,
        start.isoformat(),
        end.isoformat(),
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


def build_bowel_report_from_rows(
    rows: list[dict],
    date_keys: list[str],
    days: int,
    start_date: str,
    end_date: str,
) -> dict:
    daily = {
        day: {
            "date": day,
            "count": 0,
            "avg_bristol": None,
            "abnormal_count": 0,
            "hard_count": 0,
            "loose_count": 0,
            "normal_count": 0,
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
            if bucket != "normal":
                day_row["abnormal_count"] += 1

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
    abnormal_count = quality_counts["hard"]["count"] + quality_counts["loose"]["count"]
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
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "dates": date_keys,
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
            "normal_rate": safe_rate(quality_counts["normal"]["count"], total_events),
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
        "attention_days": attention_days,
        "no_record_dates": no_record_days,
        "insights": build_bowel_insights(
            total_events=total_events,
            avg_bristol=safe_average(bristol_values),
            abnormal_rate=safe_rate(abnormal_count, total_events),
            urgent_count=urgent_count,
            frequent_days=len(frequent_days),
            no_record_days=len(no_record_days),
            days=days,
        ),
    }


def build_medication_report_from_rows(
    rows: list[dict],
    date_keys: list[str],
    days: int,
    start_date: str,
    end_date: str,
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
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "dates": date_keys,
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
            days=days,
        ),
    }


def bristol_quality_bucket(bristol_type: int) -> str:
    for key, config in QUALITY_BUCKETS.items():
        if bristol_type in config["levels"]:
            return key
    return "normal"


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
    if row["hard_count"]:
        reasons.append(f"偏硬 {row['hard_count']} 次")
    if row["loose_count"]:
        reasons.append(f"偏稀 {row['loose_count']} 次")
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
            insights.append("整体形态偏稀，后续可以重点对照饮食、用药和急迫感。")
        elif avg_bristol <= 2.5:
            insights.append("整体形态偏硬，后续可以留意无排便日、饮水和运动。")
        else:
            insights.append("平均布里斯托等级处在相对可观察区间，重点看波动日。")

    if abnormal_rate >= 30:
        insights.append(f"偏硬或偏稀记录占 {abnormal_rate}%，建议优先查看这些日期前后的饮食和用药。")

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
