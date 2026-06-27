from __future__ import annotations

import hashlib
import json
import sqlite3

from .ai_provider import OpenAIJsonProvider
from .config import (
    DB_PATH,
    MAX_UPLOAD_BYTES,
    OPENAI_MEAL_MODEL,
    OPENAI_REPORT_MODEL,
)
from .reports import build_report


DISCLAIMER = "仅用于个人记录复盘，不替代医生建议；如症状持续、加重或出现警讯，请咨询医生。"

MEAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "foods_text": {"type": "string"},
        "visible_foods": {"type": "array", "items": {"type": "string"}},
        "possible_ingredients": {"type": "array", "items": {"type": "string"}},
        "meal_type_guess": {
            "type": "string",
            "enum": ["早餐", "午餐", "晚餐", "加餐", "不确定"],
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "needs_review": {"type": "boolean"},
        "review_notes": {"type": "string"},
    },
    "required": [
        "foods_text",
        "visible_foods",
        "possible_ingredients",
        "meal_type_guess",
        "confidence",
        "needs_review",
        "review_notes",
    ],
}

REPORT_INSIGHTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "stable_signals": {"type": "array", "items": {"type": "string"}},
        "attention_signals": {"type": "array", "items": {"type": "string"}},
        "possible_correlations": {"type": "array", "items": {"type": "string"}},
        "next_tracking_suggestions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "disclaimer": {"type": "string"},
    },
    "required": [
        "summary",
        "stable_signals",
        "attention_signals",
        "possible_correlations",
        "next_tracking_suggestions",
        "confidence",
        "disclaimer",
    ],
}


def analyze_meal(payload: dict, *, user_email: str = "") -> dict:
    text = str(payload.get("text") or "").strip()
    image_data_url = payload.get("photo_data_url")
    if not text and not image_data_url:
        raise ValueError("请先上传照片或填写文字描述")
    if image_data_url and not is_supported_image_data_url(image_data_url):
        raise ValueError("照片格式不正确")
    if image_data_url and len(image_data_url.encode("utf-8")) > MAX_UPLOAD_BYTES * 2:
        raise ValueError("照片太大，请先压缩后再识别")

    model = OPENAI_MEAL_MODEL
    provider = OpenAIJsonProvider()
    input_summary = {
        "feature_type": "meal_analysis",
        "text_length": len(text),
        "has_image": bool(image_data_url),
        "image_sha256": hash_text(image_data_url) if image_data_url else "",
        "photo_filename": str(payload.get("photo_filename") or "")[:160],
    }

    content = [
        {
            "type": "input_text",
            "text": (
                "你是一个饮食记录结构化助手。根据用户提供的饮食照片和文字，"
                "提取可见食物和可能配料。不要做医疗诊断，不要估算热量，"
                "无法确认的内容放到 possible_ingredients 或 review_notes。"
                f"\n\n用户文字描述：{text or '未填写'}"
            ),
        }
    ]
    if image_data_url:
        content.append({"type": "input_image", "image_url": image_data_url, "detail": "low"})

    try:
        analysis = provider.generate_json(
            model=model,
            content=content,
            schema_name="meal_analysis",
            schema=MEAL_SCHEMA,
        )
    except RuntimeError as exc:
        run_id = record_ai_analysis_run(
            feature_type="meal_analysis",
            provider=provider.provider_name,
            model=model,
            input_summary=input_summary,
            error=safe_error_text(exc),
            user_email=user_email,
            related_table="meals",
        )
        raise RuntimeError(f"{exc} (AI run #{run_id})") from exc

    run_id = record_ai_analysis_run(
        feature_type="meal_analysis",
        provider=provider.provider_name,
        model=model,
        input_summary=input_summary,
        output=analysis,
        user_email=user_email,
        related_table="meals",
    )
    return {
        "provider": provider.provider_name,
        "model": model,
        "analysis": analysis,
        "analysis_run_id": run_id,
    }


def analyze_report_insights(
    conn: sqlite3.Connection,
    *,
    module: str,
    end_date_text: str | None,
    days: int,
    user_email: str = "",
) -> dict:
    report = build_report(conn, module, end_date_text, days)
    record_count = report_record_count(report)
    input_summary = {
        "feature_type": "report_insights",
        "module": report.get("module"),
        "range": report.get("range"),
        "record_count": record_count,
    }

    if record_count <= 0:
        analysis = insufficient_report_analysis(report)
        run_id = record_ai_analysis_run(
            feature_type="report_insights",
            provider="local",
            model="none",
            input_summary=input_summary,
            output=analysis,
            user_email=user_email,
            report_module=report.get("module"),
            report_range=report.get("range") or {},
        )
        return {
            "provider": "local",
            "model": "none",
            "skipped_model": True,
            "analysis": analysis,
            "analysis_run_id": run_id,
        }

    model = OPENAI_REPORT_MODEL
    provider = OpenAIJsonProvider()
    ai_payload = {
        "report": compact_report_for_ai(report),
        "context": fetch_report_context(conn, report),
    }
    content = [
        {
            "type": "input_text",
            "text": (
                "你是 IBS Fighter 的个人记录复盘助手。请只基于输入 JSON 做观察，"
                "不要诊断疾病，不要给处方、剂量、治疗方案，也不要断言因果。"
                "重点解释 Bristol 4-5 安全率、非安全排便间隔、越界日期，"
                "以及饮食、用药、体重、痔疮记录中可观察但不确定的关联。"
                "输出中文，短句，具体到记录现象。disclaimer 必须使用："
                f"{DISCLAIMER}\n\n输入 JSON："
                f"{json.dumps(ai_payload, ensure_ascii=False, separators=(',', ':'))}"
            ),
        }
    ]

    try:
        analysis = provider.generate_json(
            model=model,
            content=content,
            schema_name="report_insights",
            schema=REPORT_INSIGHTS_SCHEMA,
            timeout=60,
        )
        analysis["disclaimer"] = DISCLAIMER
    except RuntimeError as exc:
        run_id = record_ai_analysis_run(
            feature_type="report_insights",
            provider=provider.provider_name,
            model=model,
            input_summary=input_summary,
            error=safe_error_text(exc),
            user_email=user_email,
            report_module=report.get("module"),
            report_range=report.get("range") or {},
        )
        raise RuntimeError(f"{exc} (AI run #{run_id})") from exc

    run_id = record_ai_analysis_run(
        feature_type="report_insights",
        provider=provider.provider_name,
        model=model,
        input_summary=input_summary,
        output=analysis,
        user_email=user_email,
        report_module=report.get("module"),
        report_range=report.get("range") or {},
    )
    return {
        "provider": provider.provider_name,
        "model": model,
        "skipped_model": False,
        "analysis": analysis,
        "analysis_run_id": run_id,
    }


def mark_ai_run_adopted(run_id: int, *, user_email: str = "") -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id, user_email
            FROM ai_analysis_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if not row:
            raise LookupError("AI 记录不存在")
        existing_email = str(row[1] or "")
        if existing_email and user_email and existing_email != user_email:
            raise PermissionError("不能标记其他账号的 AI 记录")
        conn.execute(
            """
            UPDATE ai_analysis_runs
            SET adopted = 1
            WHERE id = ?
            """,
            (run_id,),
        )
    return {"ok": True, "analysis_run_id": run_id, "adopted": True}


def record_ai_analysis_run(
    *,
    feature_type: str,
    provider: str,
    model: str,
    input_summary: dict,
    output: dict | None = None,
    error: str | None = None,
    user_email: str = "",
    related_table: str | None = None,
    related_record_id: int | None = None,
    report_module: str | None = None,
    report_range: dict | None = None,
) -> int:
    report_range = report_range or {}
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO ai_analysis_runs (
                feature_type, provider, model, input_summary_hash, output_json,
                adopted, error, user_email, related_table, related_record_id,
                report_module, report_start_date, report_end_date, report_days
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feature_type,
                provider,
                model,
                hash_json(input_summary),
                json.dumps(output, ensure_ascii=False) if output is not None else None,
                error,
                user_email,
                related_table,
                related_record_id,
                report_module,
                report_range.get("start_date"),
                report_range.get("end_date"),
                report_range.get("requested_days") or report_range.get("days"),
            ),
        )
        return int(cursor.lastrowid)


def compact_report_for_ai(report: dict) -> dict:
    module = report.get("module")
    common = {
        "module": module,
        "range": report.get("range"),
        "summary": report.get("summary"),
        "insights": report.get("insights"),
        "no_record_dates_count": len(report.get("no_record_dates") or []),
    }
    if module == "bowel":
        common.update(
            {
                "attention_days": report.get("attention_days"),
                "bristol_distribution": report.get("bristol_distribution"),
                "quality_distribution": report.get("quality_distribution"),
                "safety_p_chart": report.get("safety_p_chart"),
                "unsafe_interval_g_chart": report.get("unsafe_interval_g_chart"),
            }
        )
    elif module == "medications":
        common.update(
            {
                "product_usage": (report.get("product_usage") or [])[:10],
                "type_distribution": report.get("type_distribution"),
                "timing_distribution": report.get("timing_distribution"),
                "high_load_days": report.get("high_load_days"),
            }
        )
    elif module == "weight":
        common.update(
            {
                "trend_points": report.get("trend_points"),
                "attention_days": report.get("attention_days"),
            }
        )
    return common


def fetch_report_context(conn: sqlite3.Connection, report: dict) -> dict:
    report_range = report.get("range") or {}
    start_date = report_range.get("start_date")
    end_date = report_range.get("end_date")
    if not start_date or not end_date:
        return {}
    return {
        "meals": fetch_meal_context(conn, start_date, end_date),
        "medications": fetch_medication_context(conn, start_date, end_date),
        "body_weights": fetch_weight_context(conn, start_date, end_date),
        "hemorrhoid_events": fetch_hemorrhoid_context(conn, start_date, end_date),
    }


def fetch_meal_context(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT eaten_at, meal_type, location, foods, symptoms_after, notes, photo_path
        FROM meals
        WHERE date(eaten_at) BETWEEN ? AND ?
        ORDER BY eaten_at ASC, id ASC
        LIMIT 60
        """,
        (start_date, end_date),
    ).fetchall()
    return [
        {
            "eaten_at": row["eaten_at"],
            "meal_type": row["meal_type"],
            "location": row["location"],
            "foods": row["foods"],
            "symptoms_after": row["symptoms_after"],
            "notes": row["notes"],
            "has_photo": bool(row["photo_path"]),
        }
        for row in rows
    ]


def fetch_medication_context(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            medications.taken_at,
            medications.quantity_value,
            medications.quantity_unit,
            medications.timing_relation,
            medications.notes,
            medication_products.product_name,
            medication_products.product_type
        FROM medications
        LEFT JOIN medication_products ON medication_products.id = medications.product_id
        WHERE date(medications.taken_at) BETWEEN ? AND ?
        ORDER BY medications.taken_at ASC, medications.id ASC
        LIMIT 80
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def fetch_weight_context(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT measured_at, weight_kg, measurement_context, notes
        FROM body_weights
        WHERE date(measured_at) BETWEEN ? AND ?
        ORDER BY measured_at ASC, id ASC
        LIMIT 40
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def fetch_hemorrhoid_context(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT occurred_at, bleeding
        FROM hemorrhoid_events
        WHERE date(occurred_at) BETWEEN ? AND ?
        ORDER BY occurred_at ASC, id ASC
        LIMIT 60
        """,
        (start_date, end_date),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def insufficient_report_analysis(report: dict) -> dict:
    report_range = report.get("range") or {}
    return {
        "summary": (
            f"{report_range.get('start_date', '')} 至 {report_range.get('end_date', '')} "
            "这个周期记录不足，暂时不适合让 AI 判断稳定性。"
        ).strip(),
        "stable_signals": [],
        "attention_signals": ["当前周期没有足够记录，安全率和异常间隔都不具备解释价值。"],
        "possible_correlations": [],
        "next_tracking_suggestions": [
            "先保持连续记录 7 天以上，再用 AI 复盘安全率和异常间隔。",
            "如果当天确实没有排便，也建议后续用备注区分“无排便”和“忘记记录”。",
        ],
        "confidence": "low",
        "disclaimer": DISCLAIMER,
    }


def report_record_count(report: dict) -> int:
    summary = report.get("summary") or {}
    for key in ("total_events", "total_records", "days_with_records"):
        value = summary.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def hash_json(value: dict) -> str:
    return hash_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def hash_text(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def safe_error_text(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:1000]


def is_supported_image_data_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,"))
