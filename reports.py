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


def build_bowel_report(
    conn: sqlite3.Connection,
    end_date_text: str | None,
    days: int,
) -> dict:
    if days not in {7, 30}:
        days = 7

    try:
        end = date.fromisoformat(end_date_text or date.today().isoformat())
    except ValueError as exc:
        raise ValueError("报表日期格式不正确") from exc

    start = end - timedelta(days=days - 1)
    date_keys = [(start + timedelta(days=index)).isoformat() for index in range(days)]
    rows = fetch_bowel_rows(conn, start.isoformat(), end.isoformat())
    return build_bowel_report_from_rows(rows, date_keys, days, start.isoformat(), end.isoformat())


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
