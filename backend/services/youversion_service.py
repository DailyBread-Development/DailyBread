import json
import logging
import os
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

from backend.services.database_service import get_bible_cache, store_bible_cache

logger = logging.getLogger(__name__)

SUPPORTED_TRANSLATIONS = ("NIV", "NLT", "NKJV")
DEFAULT_TIMEZONE = "UTC"
_DAILY_CONTENT_CACHE: dict[str, dict[str, Any]] = {}


class _OpenGraphImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta" or self.image_url:
            return
        attributes = {key.lower(): value for key, value in attrs}
        if attributes.get("property", "").lower() == "og:image":
            content = attributes.get("content")
            if content and content.strip():
                self.image_url = content.strip()


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _translation_environment_map() -> dict[str, dict[str, str | None]]:
    return {
        "NIV": {"id": _env_first("youversion_niv_id", "YVP_NIV_ID", "NIV_YOUVERSION_ID"), "name": "New International Version"},
        "NLT": {"id": _env_first("youversion_nlt_id", "YVP_NLT_ID", "NLT_YOUVERSION_ID"), "name": "New Living Translation"},
        "NKJV": {"id": _env_first("youversion_nkjv_id", "YVP_NKJV_ID", "NKJV_YOUVERSION_ID"), "name": "New King James Version"},
    }


def get_translation_id(translation: str | None) -> str | None:
    normalized = (translation or "").strip().upper()
    if not normalized:
        return None
    env_map = _translation_environment_map()
    if normalized in env_map:
        return env_map[normalized].get("id")
    for label, details in env_map.items():
        if label == normalized:
            return details.get("id")
    return None


def get_translation_name(translation: str | None) -> str:
    value = (translation or "").strip().upper()
    mapping = _translation_environment_map()
    return mapping.get(value, {}).get("name") or value or "Unknown translation"


def get_daily_verse_translation_options() -> list[str]:
    return ["NIV"]


def get_daily_verse_timezone() -> ZoneInfo:
    timezone_name = _env_first("DAILY_VERSE_TIMEZONE", "APP_TIMEZONE", "TIMEZONE", "TZ") or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        logger.warning("Invalid DAILY_VERSE_TIMEZONE=%s; using %s", timezone_name, DEFAULT_TIMEZONE)
        return ZoneInfo(DEFAULT_TIMEZONE)


def get_today_date_string() -> str:
    return datetime.now(get_daily_verse_timezone()).date().isoformat()


def get_day_of_year_for_date(date_text: str | None = None) -> int:
    target_date = datetime.fromisoformat(date_text).date() if date_text else datetime.now(get_daily_verse_timezone()).date()
    return int(target_date.timetuple().tm_yday)


def build_daily_cache_key(date_text: str | None = None, translation: str | None = None) -> str:
    target_date = date_text or get_today_date_string()
    return f"daily_verse:{target_date}:{(translation or get_daily_verse_translation_options()[0]).upper()}"


def _request_json(url: str, headers: dict[str, str], *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.strip().replace(".", "", 1).isdigit() else 2 ** (attempt - 1)
                if attempt < 4:
                    logger.warning("YouVersion rate limit hit for %s; retrying in %ss", url, delay)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
            if response.status_code >= 500 and attempt < 4:
                delay = 2 ** attempt
                logger.warning("YouVersion temporary failure (%s) for %s; retrying in %ss", response.status_code, url, delay)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {}
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise
        except ValueError as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError("Invalid YouVersion response") from exc
    if last_error:
        raise last_error
    raise RuntimeError("YouVersion request failed.")


def _youversion_headers() -> dict[str, str]:
    app_key = _env_first("youversion_token", "YVP_APP_KEY", "YVP_TOKEN")
    if not app_key:
        raise RuntimeError("YouVersion app key is not configured.")
    return {"X-YVP-App-Key": app_key}


def _decompose_reference_value(value: str | None) -> tuple[str, str]:
    if not value:
        return ("", "")
    if " | " in value:
        parts = value.split(" | ", 1)
        return parts[0].strip(), parts[1].strip()
    return (value.strip(), value.strip())


def _compose_reference_value(passage_id: str | None, display_reference: str | None) -> str:
    if not passage_id and not display_reference:
        return ""
    if passage_id and display_reference and str(passage_id).strip() != str(display_reference).strip():
        return f"{passage_id.strip()} | {display_reference.strip()}"
    return (display_reference or passage_id or "").strip()


def _extract_image_url(payload: dict[str, Any]) -> str | None:
    for key in ("image_url", "imageUrl", "image"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested_url = value.get("url") or value.get("image_url") or value.get("imageUrl")
            if isinstance(nested_url, str) and nested_url.strip():
                return nested_url.strip()
    return None


def _resolve_daily_verse_image() -> str | None:
    try:
        response = requests.get("https://www.bible.com/verse-of-the-day", timeout=15)
        response.raise_for_status()
        parser = _OpenGraphImageParser()
        parser.feed(response.text)
        if parser.image_url:
            logger.info("Daily verse image resolved successfully")
        return parser.image_url
    except Exception as exc:  # pragma: no cover - external service failure
        logger.warning("Failed to resolve YouVersion daily verse image: %s", exc)
        return None


def _normalize_daily_verse(
    payload: dict[str, Any],
    date_text: str,
    translation_label: str,
    passage_id: str | None = None,
    image_url: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid YouVersion response payload.")
    passage = payload.get("passage") if isinstance(payload.get("passage"), dict) else payload
    if not isinstance(passage, dict):
        raise ValueError("YouVersion passage data was not returned.")

    text = str(passage.get("text") or passage.get("content") or "").strip()
    reference = str(passage.get("reference") or passage.get("title") or "").strip()
    full_reference = _compose_reference_value(passage_id or passage.get("id"), reference)
    if not text:
        raise ValueError("YouVersion passage text was empty.")

    translation_id = get_translation_id(translation_label)
    passage_identifier = str(passage_id or passage.get("id") or "").strip()
    stored_reference = full_reference if passage_identifier else reference
    return {
        "reference": (reference or full_reference).strip(),
        "text": text,
        "translation": translation_label.upper(),
        "translation_name": get_translation_name(translation_label),
        "date": date_text,
        "passage_id": passage_identifier,
        "cache_key": build_daily_cache_key(date_text, translation_label),
        "translation_id": translation_id,
        "stored_reference": stored_reference,
        "image_url": image_url,
    }


def _get_passage_for_translation(date_text: str, translation_label: str) -> dict[str, Any]:
    base_url = _env_first("youversion_base_url", "YOUVERSION_BASE_URL", "YVP_BASE_URL") or "https://api.youversion.com/v1"
    translation_id = get_translation_id(translation_label)
    if not translation_id:
        raise ValueError(f"No YouVersion ID configured for translation {translation_label}.")

    day = get_day_of_year_for_date(date_text)
    verse_of_day_url = f"{base_url.rstrip('/')}/verse_of_the_days/{day}"
    verse_of_day: Any = _request_json(verse_of_day_url, _youversion_headers())
    if isinstance(verse_of_day, list):
        if not verse_of_day:
            raise ValueError("YouVersion returned no verse of the day for this date.")
        verse_of_day = verse_of_day[0]
    passage_id = str(verse_of_day.get("passage_id") or verse_of_day.get("passageId") or "").strip()
    if not passage_id:
        raise ValueError("YouVersion did not return a passage ID for the daily verse.")

    passage_url = f"{base_url.rstrip('/')}/bibles/{translation_id}/passages/{passage_id}"
    passage_payload = _request_json(passage_url, _youversion_headers())
    return _normalize_daily_verse(
        passage_payload,
        date_text,
        translation_label,
        passage_id,
        _extract_image_url(verse_of_day) or _extract_image_url(passage_payload),
    )


def _try_verse_for_translation(date_text: str, translation_label: str) -> dict[str, Any] | None:
    try:
        item = _get_passage_for_translation(date_text, translation_label)
        return item
    except Exception as exc:  # pragma: no cover - exercised via service fallback logic
        logger.warning("Daily verse lookup failed for %s on %s: %s", translation_label, date_text, exc)
        return None


def get_today() -> dict[str, Any] | None:
    date_text = get_today_date_string()
    configured_translation = "NIV"
    fallback_translation = ""

    cache_key = build_daily_cache_key(date_text, configured_translation)
    cached_content = _DAILY_CONTENT_CACHE.get(cache_key)
    if cached_content:
        return dict(cached_content)

    cached = get_bible_cache(cache_key)
    if cached and cached.get("text"):
        image_url = cached.get("image_url") or _resolve_daily_verse_image()
        passage_id, display_reference = _decompose_reference_value(cached.get("reference"))
        result = {
            "reference": display_reference or cached.get("reference") or "Daily verse",
            "text": cached.get("text"),
            "translation": "NIV",
            "translation_name": get_translation_name("NIV"),
            "date": date_text,
            "passage_id": passage_id,
            "cache_key": cache_key,
            "image_url": image_url,
        }
        _DAILY_CONTENT_CACHE[cache_key] = result
        return dict(result)

    translation_order = ["NIV"]

    last_error: Exception | None = None
    for translation_label in translation_order:
        result = _try_verse_for_translation(date_text, translation_label)
        if result:
            store_bible_cache(
                result["cache_key"],
                result.get("stored_reference") or result["reference"],
                result["text"],
                result["translation"],
                result.get("image_url"),
            )
            _DAILY_CONTENT_CACHE[cache_key] = result
            logger.info(
                "Daily verse provider: YouVersion; translation: NIV; reference: %s; image retrieved: %s",
                result["reference"],
                bool(result.get("image_url")),
            )
            if not result.get("image_url"):
                logger.warning("Daily verse image retrieval failed: YouVersion returned no image URL.")
            return dict(result)
        last_error = RuntimeError(f"Failed to fetch daily verse for {translation_label}.")
        if translation_label != configured_translation:
            logger.warning("Falling back from %s to %s for the daily verse because the primary YouVersion lookup did not succeed.", configured_translation, translation_label)

    if last_error:
        logger.warning("Daily verse lookup failed for %s; using the most recent cached verse if available.", configured_translation)

    recent = get_latest_daily_verse_cache()
    if recent and recent.get('text'):
        image_url = recent.get("image_url") or _resolve_daily_verse_image()
        passage_id, display_reference = _decompose_reference_value(recent.get("reference"))
        cached_date = recent.get("cache_key", "").split(":", 2)[1] if ":" in recent.get("cache_key", "") else date_text
        result = {
            "reference": display_reference or recent.get("reference") or "Daily verse",
            "text": recent.get("text"),
            "translation": "NIV",
            "translation_name": get_translation_name("NIV"),
            "date": cached_date,
            "passage_id": passage_id,
            "cache_key": recent.get("cache_key") or cache_key,
            "image_url": image_url,
        }
        _DAILY_CONTENT_CACHE[cache_key] = result
        return dict(result)

    return None


def get_latest_daily_verse_cache() -> dict[str, Any] | None:
    try:
        from backend.services import database_service
        return database_service.get_latest_daily_verse_cache()
    except Exception:
        return None
