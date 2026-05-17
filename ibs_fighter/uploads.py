from __future__ import annotations

import base64
import binascii
from datetime import date
from uuid import uuid4

from .config import IMAGE_EXTENSIONS, MAX_UPLOAD_BYTES, UPLOADS_DIR


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
