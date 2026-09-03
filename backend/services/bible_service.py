import os
import re
from pathlib import Path
import traceback
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import requests

from backend.services.database_service import get_bible_cache, store_bible_cache

# Load environment variables from .env file if it exists
BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        load_dotenv(env_path, override=False)

def _get_api_config() -> Dict[str, str]:
    api_key = os.getenv("bible_api_key")

    base_url = os.getenv(
        "bible_api_base_url",
        "https://api.scripture.api.bible/v1"
    ).rstrip("/")

    bible_id = os.getenv("bible_id")

    if not bible_id:
        # Fallback to NIV if no default is configured
        bible_id = os.getenv("niv_bible_id")

    if not bible_id:
        raise ValueError(
            "No Bible ID configured. Set bible_id or niv_bible_id."
        )

    if not api_key:
        raise ValueError(
            "Bible API key is missing."
        )

    return {
        "api_key": api_key,
        "base_url": base_url,
        "bible_id": bible_id,
    }


# Normalizes the response from the Bible API to ensure we have consistent fields for reference, text, and translation.
def _api_headers() -> Dict[str, str]:
    api_config = _get_api_config()
    if not api_config.get("api_key"):
        raise RuntimeError("API_BIBLE_KEY is required for api.bible lookups.")

    return {"api-key": api_config["api_key"]}


def _normalize_passage(
    data: Optional[Dict[str, Any]],
    fallback_reference: str,
    fallback_translation: Optional[str] = None,
) -> Dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    passage = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    if not isinstance(passage, dict):
        raise ValueError("Invalid api.bible response; passage payload is missing.")

    text = str(passage.get("content") or "").strip()
    actual_reference = passage.get("reference") or fallback_reference
    translation = passage.get("bibleId") or fallback_translation or _get_api_config()["bible_id"]

    if not text:
        raise ValueError("Invalid api.bible response; verse text is missing.")

    return {
        "reference": actual_reference,
        "text": text,
        "translation": str(translation).strip() if translation else None,
    }


def _parse_translation_token(token: str) -> Optional[Dict[str, str]]:
    raw_token = token.strip()
    if not raw_token:
        return None

    if ":" in raw_token:
        label, translation_id = raw_token.split(":", 1)
        label = label.strip().upper()
        translation_id = translation_id.strip()
        if label and translation_id:
            return {"label": label, "translation_id": translation_id}
        return None

    label = raw_token.upper()
    env_name = f"{raw_token.lower()}_bible_id"
    translation_id = os.getenv(env_name)
    print("Looking for:", env_name)
    print("Found:", os.getenv(env_name))
    if translation_id:
        return {"label": label, "translation_id": translation_id}
    return None


def _parse_reference_query(query: str) -> Dict[str, Any]:
    normalized_query = query.strip()

    if not normalized_query:
        return {
            "reference": "",
            "translations": [],
            "translation_labels": [],
            "query": "",
        }

    parts = normalized_query.split(maxsplit=1)

    if len(parts) == 2:
        prefix = parts[0]
        reference = parts[1].strip()

        translation_ids: List[str] = []
        translation_labels: List[str] = []

        for token in prefix.split("/"):
            # Only parse as translation if an environment variable exists.
            env_name = f"{token.lower()}_bible_id"
            translation_id = os.getenv(env_name)

            if not translation_id:
                translation_ids = []
                translation_labels = []
                break

            translation_ids.append(translation_id)
            translation_labels.append(token.upper())

        if translation_ids:
            return {
                "reference": reference,
                "translations": translation_ids,
                "translation_labels": translation_labels,
                "query": normalized_query,
            }

    return {
        "reference": normalized_query,
        "translations": [],
        "translation_labels": [],
        "query": normalized_query,
    }


# Resolves a verse reference to its passage ID using the Bible API.
def _find_passage_id(reference: str, bible_id: Optional[str] = None) -> str:
    api_config = _get_api_config()
    selected_bible_id = bible_id or api_config["bible_id"]
    response = requests.get(
        f"{api_config['base_url']}/bibles/{selected_bible_id}/search",
        headers=_api_headers(),
        params={"query": reference, "limit": 1, "sort": "relevance"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    passages = data.get("passages") or []
    if not passages:
        raise ValueError("Verse not found.")

    passage_id = passages[0].get("id")
    if not passage_id:
        raise ValueError("api.bible search did not return a passage ID.")
    return str(passage_id)


# Resolves a verse reference to its text and translation using the Bible API, with caching to reduce API calls.
def _get_translation_label(translation_id: Optional[str], requested_labels: Optional[List[str]] = None) -> Optional[str]:
    if not translation_id:
        return None
    if requested_labels:
        if len(requested_labels) == 1:
            return requested_labels[0]
        return "/".join(requested_labels)

    env_names = [
        "API_BIBLE_ID",
        "api_bible_id",
        "BIBLE_API_ID",
        "bible_api_id",
    ]
    for env_name in env_names:
        env_value = os.getenv(env_name)
        if env_value == translation_id:
            return env_name.replace("_bible_id", "").upper()
    return str(translation_id)


# Resolves a verse reference to its text and translation using the Bible API, with caching to reduce API calls.
def resolve_verse_reference(reference: str) -> Optional[Dict[str, Any]]:
    reference = reference.strip()
    if not reference:
        return None

    parsed_query = _parse_reference_query(reference)
    selected_reference = parsed_query["reference"]
    selected_translations = parsed_query["translations"]
    if not selected_translations:
        selected_translations = [_get_api_config()["bible_id"]]

    cache_key = f"{'|'.join(selected_translations)}::{selected_reference}"
    cached = get_bible_cache(cache_key)
    if cached and cached.get("text"):
        return {
            "reference": cached.get("reference", selected_reference),
            "text": cached.get("text"),
            "translation": cached.get("translation"),
            "translation_label": _get_translation_label(
                cached.get("translation"),
                parsed_query.get("translation_labels") or [],
            ),
        }

    last_error: Optional[Exception] = None
    for translation_id in selected_translations:
        try:
            passage_id = _find_passage_id(selected_reference, translation_id)
            api_config = _get_api_config()
            response = requests.get(
                f"{api_config['base_url']}/bibles/{translation_id}/passages/{passage_id}",
                headers=_api_headers(),
                params={
                    "content-type": "text",
                    "include-notes": "false",
                    "include-titles": "false",
                    "include-chapter-numbers": "false",
                    "include-verse-numbers": "true",
                    "include-verse-spans": "false",
                },
                timeout=15,
            )
            response.raise_for_status()
            bible_data = _normalize_passage(response.json(), selected_reference, translation_id)
            bible_data["translation_label"] = _get_translation_label(
                bible_data.get("translation"),
                parsed_query.get("translation_labels") or [],
            )
            store_bible_cache(
                cache_key,
                selected_reference,
                bible_data["text"],
                bible_data.get("translation"),
            )
            return bible_data
        except Exception as exc:
             traceback.print_exc()
             last_error = exc
        continue

    if last_error:
        raise last_error
    raise ValueError("Verse not found.")
