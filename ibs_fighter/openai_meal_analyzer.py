from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import MAX_UPLOAD_BYTES, OPENAI_API_KEY, OPENAI_MEAL_MODEL


RESPONSES_URL = "https://api.openai.com/v1/responses"

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


def analyze_meal(payload: dict) -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError("未配置 OPENAI_API_KEY")

    text = str(payload.get("text") or "").strip()
    image_data_url = payload.get("photo_data_url")
    if not text and not image_data_url:
        raise ValueError("请先上传照片或填写文字描述")
    if image_data_url and not _is_supported_data_url(image_data_url):
        raise ValueError("照片格式不正确")
    if image_data_url and len(image_data_url.encode("utf-8")) > MAX_UPLOAD_BYTES * 2:
        raise ValueError("照片太大，请先压缩后再识别")

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

    request_payload = {
        "model": OPENAI_MEAL_MODEL,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "meal_analysis",
                "strict": True,
                "schema": MEAL_SCHEMA,
            }
        },
    }

    response = _post_json(request_payload)
    result_text = response.get("output_text") or _extract_output_text(response)
    if not result_text:
        raise RuntimeError("OpenAI 没有返回可解析结果")

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI 返回结果不是有效 JSON") from exc

    return {
        "model": OPENAI_MEAL_MODEL,
        "analysis": result,
    }


def _post_json(payload: dict) -> dict:
    request = urllib.request.Request(
        RESPONSES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API 调用失败: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接 OpenAI API，请检查网络") from exc


def _extract_output_text(response: dict) -> str | None:
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    return None


def _is_supported_data_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,"))
