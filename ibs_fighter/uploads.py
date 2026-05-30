from __future__ import annotations

import base64
import binascii
from io import BytesIO
from datetime import date
from pathlib import Path
from uuid import uuid4

from .config import (
    IMAGE_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MEAL_PHOTO_MAX_DIMENSION,
    MEAL_PHOTO_TARGET_BYTES,
    UPLOADS_DIR,
)


OUTPUT_EXTENSION = ".jpg"
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
MIN_JPEG_QUALITY = 45
QUALITY_STEPS = (85, 80, 75, 70, 65, 60, 55, 50, MIN_JPEG_QUALITY)


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

    compressed_bytes = compress_meal_photo(image_bytes)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}-{uuid4().hex}{OUTPUT_EXTENSION}"
    target = UPLOADS_DIR / filename
    target.write_bytes(compressed_bytes)

    return {
        "photo_path": f"/uploads/{filename}",
        "photo_filename": str(original_name).strip() if original_name else filename,
    }


def recompress_uploads_directory(
    uploads_dir: Path = UPLOADS_DIR,
    *,
    dry_run: bool = False,
) -> dict:
    uploads_dir = Path(uploads_dir).expanduser()
    result = {
        "ok": True,
        "uploads_dir": str(uploads_dir),
        "dry_run": dry_run,
        "scanned": 0,
        "compressed": 0,
        "skipped": 0,
        "errors": 0,
        "bytes_before": 0,
        "bytes_after": 0,
        "bytes_saved": 0,
        "files": [],
    }

    if not uploads_dir.exists():
        return result

    for path in sorted(uploads_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in JPEG_EXTENSIONS:
            result["skipped"] += 1
            result["files"].append({"path": str(path), "action": "skipped_non_jpeg"})
            continue

        result["scanned"] += 1
        try:
            original_bytes = path.read_bytes()
            original_size = len(original_bytes)
            if original_size <= MEAL_PHOTO_TARGET_BYTES:
                result["skipped"] += 1
                result["bytes_before"] += original_size
                result["bytes_after"] += original_size
                result["files"].append(
                    {
                        "path": str(path),
                        "action": "skipped_under_target",
                        "before": original_size,
                        "after": original_size,
                    }
                )
                continue

            compressed_bytes = compress_meal_photo(original_bytes)
            compressed_size = len(compressed_bytes)
            result["bytes_before"] += original_size

            if compressed_size >= original_size:
                result["skipped"] += 1
                result["bytes_after"] += original_size
                result["files"].append(
                    {
                        "path": str(path),
                        "action": "skipped_already_smaller",
                        "before": original_size,
                        "after": original_size,
                    }
                )
                continue

            result["compressed"] += 1
            result["bytes_after"] += compressed_size
            result["bytes_saved"] += original_size - compressed_size
            result["files"].append(
                {
                    "path": str(path),
                    "action": "would_compress" if dry_run else "compressed",
                    "before": original_size,
                    "after": compressed_size,
                }
            )

            if not dry_run:
                temp_path = path.with_name(f".{path.name}.tmp")
                temp_path.write_bytes(compressed_bytes)
                temp_path.replace(path)
        except Exception as exc:
            result["errors"] += 1
            result["files"].append({"path": str(path), "action": "error", "error": str(exc)})

    return result


def compress_meal_photo(image_bytes: bytes) -> bytes:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError("照片压缩依赖 Pillow 未安装，请重新安装 requirements.txt") from exc

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            if getattr(image, "is_animated", False):
                image.seek(0)
            image = flatten_to_rgb(image, Image)
            image.thumbnail(
                (MEAL_PHOTO_MAX_DIMENSION, MEAL_PHOTO_MAX_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            return encode_under_target(image)
    except UnidentifiedImageError as exc:
        raise ValueError("照片内容不是有效图片") from exc


def flatten_to_rgb(image, image_module):
    if image.mode == "RGB":
        return image.copy()

    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = image_module.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")

    return image.convert("RGB")


def encode_under_target(image) -> bytes:
    current = image.copy()
    best = b""

    while True:
        for quality in QUALITY_STEPS:
            encoded = encode_jpeg(current, quality)
            best = encoded
            if len(encoded) <= MEAL_PHOTO_TARGET_BYTES:
                return encoded

        width, height = current.size
        longest_side = max(width, height)
        if longest_side <= 720:
            return best

        scale = max(720 / longest_side, 0.85)
        next_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        current = current.resize(next_size, image_resampling_lanczos())


def encode_jpeg(image, quality: int) -> bytes:
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return output.getvalue()


def image_resampling_lanczos():
    from PIL import Image

    return Image.Resampling.LANCZOS
