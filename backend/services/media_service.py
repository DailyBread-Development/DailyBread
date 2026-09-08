import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
FORMAT_TO_EXTENSION = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_media_storage_dir() -> Path:
    configured = os.getenv("MEDIA_STORAGE_PATH") or os.getenv("media_storage_path")
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = (_project_root() / candidate).resolve()
    else:
        candidate = (_project_root() / "uploads").resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def get_public_base_url(request: Any | None = None) -> str:
    configured = os.getenv("PUBLIC_BASE_URL") or os.getenv("public_base_url")
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    return "http://localhost:8000"


def detect_image_format(file_bytes: bytes, filename: str | None = None) -> str:
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            image.load()
            detected = image.format or ("PNG" if (filename or "").lower().endswith(".png") else None)
            if not detected:
                raise ValueError("Unable to determine image format.")
            format_name = str(detected).upper()
            if format_name not in ALLOWED_IMAGE_FORMATS:
                raise ValueError(f"Unsupported image format: {format_name}.")
            return format_name
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        ext = Path(filename or "").suffix.lower()
        if ext and ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise ValueError(f"Unsupported image format: {ext.lstrip('.').upper()}.") from exc
        if isinstance(exc, ValueError) and "Unsupported image format" in str(exc):
            raise
        raise ValueError("Invalid or corrupted image file.") from exc


def validate_image_upload(
    file_bytes: bytes,
    filename: str | None = None,
    *,
    max_size_bytes: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> dict[str, Any]:
    if not file_bytes:
        raise ValueError("No file data was uploaded.")

    configured_max = max_size_bytes
    if configured_max is None:
        configured_max = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024
    if len(file_bytes) > configured_max:
        raise ValueError(f"Upload size exceeds the {configured_max / (1024 * 1024):.0f} MB limit.")

    format_name = detect_image_format(file_bytes, filename)
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            image.load()
            width, height = image.size
    except (UnidentifiedImageError, OSError):
        raise ValueError("Invalid or corrupted image file.") from None

    width_limit = max_width if max_width is not None else int(os.getenv("MAX_IMAGE_WIDTH", "4096"))
    height_limit = max_height if max_height is not None else int(os.getenv("MAX_IMAGE_HEIGHT", "4096"))
    if width > width_limit or height > height_limit:
        raise ValueError(f"Image dimensions exceed the {width_limit}x{height_limit} limit.")

    return {
        "format": format_name,
        "width": width,
        "height": height,
        "size": len(file_bytes),
    }


def generate_media_filename(filename: str | None, image_format: str | None = None) -> str:
    extension = FORMAT_TO_EXTENSION.get((image_format or "").upper())
    if extension is None:
        suffix = Path(filename or "upload").suffix.lower()
        extension = {
            ".png": ".png",
            ".jpg": ".jpg",
            ".jpeg": ".jpg",
            ".webp": ".webp",
            ".gif": ".gif",
        }.get(suffix, ".png")
    return f"{uuid.uuid4().hex}{extension}"


def build_media_url(filename: str, request: Any | None = None) -> str:
    safe_filename = quote(filename, safe="")
    return f"{get_public_base_url(request).rstrip('/')}/media/{safe_filename}"


def save_uploaded_media(file_bytes: bytes, filename: str | None, request: Any | None = None) -> dict[str, Any]:
    validated = validate_image_upload(file_bytes, filename)
    storage_dir = get_media_storage_dir()
    storage_name = generate_media_filename(filename, validated["format"])
    target_path = storage_dir / storage_name
    target_path.write_bytes(file_bytes)
    return {
        "filename": storage_name,
        "storage_path": str(target_path),
        "url": build_media_url(storage_name, request),
        "width": validated["width"],
        "height": validated["height"],
        "size": validated["size"],
        "format": validated["format"],
    }
