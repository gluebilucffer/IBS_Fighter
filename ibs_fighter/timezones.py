from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DEFAULT_TIMEZONE, LEGACY_TIMEZONE


TIME_FIELDS = {
    "bowel_movements": ("occurred_at", "occurred_timezone", "occurred_at_utc"),
    "meals": ("eaten_at", "eaten_timezone", "eaten_at_utc"),
    "medications": ("taken_at", "taken_timezone", "taken_at_utc"),
    "exercises": ("started_at", "started_timezone", "started_at_utc"),
}


def resolve_timezone(value: object, fallback: str = DEFAULT_TIMEZONE) -> str:
    timezone_name = str(value or fallback).strip() or fallback
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区: {timezone_name}") from exc
    return timezone_name


def local_datetime_to_utc(value: str, timezone_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("时间不能为空")

    try:
        local_dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"时间格式不正确: {text}") from exc

    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=ZoneInfo(timezone_name))

    utc_dt = local_dt.astimezone(timezone.utc).replace(microsecond=0)
    return utc_dt.isoformat().replace("+00:00", "Z")


def apply_time_metadata(table: str, payload: dict, data: dict) -> dict:
    fields = TIME_FIELDS.get(table)
    if not fields:
        return data

    local_field, timezone_field, utc_field = fields
    if local_field not in data:
        return data

    timezone_name = resolve_timezone(
        payload.get("client_timezone") or payload.get(timezone_field) or DEFAULT_TIMEZONE
    )
    data[timezone_field] = timezone_name
    data[utc_field] = local_datetime_to_utc(data[local_field], timezone_name)
    return data


def legacy_utc_for_local(value: str) -> tuple[str, str]:
    timezone_name = resolve_timezone(LEGACY_TIMEZONE, "Pacific/Port_Moresby")
    return timezone_name, local_datetime_to_utc(value, timezone_name)
