import httpx
from datetime import datetime
from typing import Any, Dict, Optional


# This module provides functionality to send messages to Discord webhooks, including error handling and payload construction.
class WebhookSenderError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


# Normalizes color input to an integer. Accepts integers, hex strings (with or without #), or None.
def _normalize_color(color: Optional[int]) -> int:
    if color is None:
        return 0
    if isinstance(color, int):
        return color
    try:
        return int(str(color).strip().lstrip("#"), 16)
    except (ValueError, TypeError):
        return 0


# Builds the payload for the Discord webhook based on the provided embed and optional Bible data.
def build_payload_from_embed(embed: Dict[str, Any], bible_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    embed_payload: Dict[str, Any] = {
        "title": embed.get("title", ""),
        "description": embed.get("description", ""),
        "color": embed.get("color"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    footer_text = embed.get("footer")
    if footer_text:
        embed_payload["footer"] = {"text": footer_text}

    if embed.get("image_url"):
        embed_payload["image"] = {"url": embed["image_url"]}
    if embed.get("thumbnail_url"):
        embed_payload["thumbnail"] = {"url": embed["thumbnail_url"]}
    if embed.get("author"):
        embed_payload["author"] = {"name": embed["author"]}

    image_url = embed.get("image_url")
    if image_url:
        embed_payload["image"] = {"url": image_url}

    if bible_data and bible_data.get("reference") and bible_data.get("text"):
        embed_payload["fields"] = [
            {
                "name": bible_data["reference"],
                "value": bible_data["text"],
                "inline": False,
            }
        ]

    payload: Dict[str, Any] = {"embeds": [embed_payload]}
    if embed.get("message_content"):
        payload["content"] = str(embed["message_content"])
    return payload


# Constructs the full Discord webhook URL from the stored webhook record. Raises an error if required information is missing.
def _build_webhook_url(webhook: Dict[str, Any]) -> str:
    webhook_id = webhook.get("discord_id")
    token = webhook.get("token")
    if not webhook_id or not token:
        raise WebhookSenderError("Invalid webhook record: missing webhook ID or token.")
    return f"https://discord.com/api/webhooks/{webhook_id}/{token}"


# Masks the webhook URL for logging purposes to avoid exposing sensitive information.
def _mask_webhook_url(url: str) -> str:
    try:
        parts = url.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:-1]) + "/<masked>"
    except Exception:
        pass
    return "<masked_webhook_url>"


# Generates a user-friendly error message based on the HTTP status code returned by Discord.
def _discord_error_message(status_code: int, response_text: str) -> str:
    if status_code == 404:
        return "Discord webhook not found or invalid."
    if status_code == 429:
        return "Discord rate limit exceeded. Please wait and try again."
    if status_code >= 500:
        return "Discord is currently unavailable. Please try again later."
    return f"Discord webhook failed with status {status_code}."


# Asynchronously sends a payload to the specified Discord webhook URL and returns a record of the delivery attempt, including success status and any error messages.
async def send_webhook(webhook: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        url = _build_webhook_url(webhook)
    except WebhookSenderError as exc:
        return {
            "webhook_id": webhook.get("discord_id"),
            "success": False,
            "status_code": exc.status_code,
            "response_text": exc.response_text,
            "error": str(exc),
        }

    masked_url = _mask_webhook_url(url)
    print("WEBHOOK DELIVERY ATTEMPT", {
        "webhook_id": webhook.get("discord_id"),
        "masked_url": masked_url,
        "payload": payload,
    })

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            return {
                "webhook_id": webhook.get("discord_id"),
                "success": False,
                "status_code": None,
                "response_text": str(exc),
                "error": "Unable to reach Discord webhook endpoint.",
            }

    response_text = response.text or ""
    status_code = response.status_code

    print("WEBHOOK DELIVERY RESPONSE", {
        "webhook_id": webhook.get("discord_id"),
        "masked_url": masked_url,
        "status_code": status_code,
        "response_text": response_text[:300],
    })

    if status_code == 204:
        return {
            "webhook_id": webhook.get("discord_id"),
            "success": True,
            "status_code": status_code,
            "response_text": response_text,
        }

    return {
        "webhook_id": webhook.get("discord_id"),
        "success": False,
        "status_code": status_code,
        "response_text": response_text,
        "error": _discord_error_message(status_code, response_text),
    }
