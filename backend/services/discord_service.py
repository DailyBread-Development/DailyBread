import base64
import os
from typing import Any, Dict, List, Optional

import requests

DISCORD_API_BASE = "https://discord.com/api/v10"
BOT_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("discord_token") or os.getenv("DISCORD_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("DISCORD_TOKEN or DISCORD_BOT_TOKEN is required for Discord REST operations.")

_cached_bot_user: Optional[Dict[str, Any]] = None


def _dailybread_avatar_data_uri() -> str:
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'><rect width='256' height='256' rx='64' fill='#f2e3b3'/><circle cx='128' cy='128' r='92' fill='#2b2b2b'/><path d='M88 92h80v24H112v18h48v22H112v18h56v24H88z' fill='#f2c96b'/></svg>"""
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('ascii')}"


# Internal helper to require a valid session for routes that need authentication. Raises ValueError if not authenticated.
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }


# Internal helper to require a valid session for routes that need authentication. Raises ValueError if not authenticated.
def _request(method: str, path: str, json: Any = None) -> Any:
    url = f"{DISCORD_API_BASE}{path}"
    response = requests.request(method, url, json=json, headers=_headers(), timeout=10)
    try:
        body = response.json()
    except ValueError:
        body = {"status_text": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Discord API {response.status_code}: {body}")
    return body


# Gets the bot's own user information, with caching to avoid unnecessary API calls.
def get_bot_user() -> Dict[str, Any]:
    global _cached_bot_user
    if _cached_bot_user is None:
        _cached_bot_user = _request("GET", "/users/@me")
    assert _cached_bot_user is not None
    return _cached_bot_user


# Checks if the bot is a member of the specified guild by attempting to fetch its member information. Returns True if the bot is in the guild, False otherwise.
def is_bot_in_guild(guild_id: str) -> bool:
    bot_user = get_bot_user()
    bot_id = bot_user.get("id")
    if not bot_id:
        return False
    try:
        _request("GET", f"/guilds/{guild_id}/members/{bot_id}")
        return True
    except RuntimeError:
        return False


# Lists all channels in the specified guild
def list_guild_channels(guild_id: str) -> List[Dict[str, Any]]:
    return _request("GET", f"/guilds/{guild_id}/channels")


def list_guild_roles(guild_id: str) -> List[Dict[str, Any]]:
    """Return roles visible to the DailyBread bot for Discord mention previews."""
    return _request("GET", f"/guilds/{guild_id}/roles")


# Creates a webhook in the specified channel with the given name, and returns the webhook information including the ID and token needed to send messages through it.
def create_webhook(channel_id: str, name: str = "DailyBread") -> Dict[str, Any]:
    payload = {
        "name": name,
        "avatar": _dailybread_avatar_data_uri(),
    }
    return _request("POST", f"/channels/{channel_id}/webhooks", json=payload)


# Sends a message through the specified webhook with the given embed payload. Returns the response from the Discord API.
def send_webhook(webhook_id: str, webhook_token: str, embed_payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://discord.com/api/v10/webhooks/{webhook_id}/{webhook_token}"
    response = requests.post(url, json=embed_payload, timeout=10)
    try:
        body = response.json()
    except ValueError:
        body = {"status_text": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Discord Webhook {response.status_code}: {body}")
    return body
