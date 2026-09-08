import base64
import os
import time
from typing import Any, Dict, List, Optional

import requests

DISCORD_API_BASE = "https://discord.com/api/v10"
BOT_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("discord_token") or os.getenv("DISCORD_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("DISCORD_TOKEN or DISCORD_BOT_TOKEN is required for Discord REST operations.")

_cached_bot_user: Optional[Dict[str, Any]] = None
_guild_member_cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_guild_role_cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_GUILD_CACHE_TTL = 60


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
    cached = _guild_role_cache.get(str(guild_id))
    if cached and time.monotonic() - cached[0] < _GUILD_CACHE_TTL:
        return cached[1]
    roles = _request("GET", f"/guilds/{guild_id}/roles")
    _guild_role_cache[str(guild_id)] = (time.monotonic(), roles)
    return roles


def list_guild_members(guild_id: str) -> List[Dict[str, Any]]:
    """Load a bounded member snapshot once per minute for mention search."""
    cache_key = str(guild_id)
    cached = _guild_member_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _GUILD_CACHE_TTL:
        return cached[1]
    members = _request("GET", f"/guilds/{guild_id}/members?limit=1000")
    _guild_member_cache[cache_key] = (time.monotonic(), members)
    return members


def search_guild_members(guild_id: str, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    query = query.strip().casefold()
    members = []
    for member in list_guild_members(guild_id):
        user = member.get("user") or {}
        username = str(user.get("username") or "")
        display_name = str(member.get("nick") or user.get("global_name") or username)
        if query and query not in display_name.casefold() and query not in username.casefold():
            continue
        members.append({"id": str(user.get("id") or ""), "display_name": display_name, "username": username, "avatar": user.get("avatar")})
    return sorted(members, key=lambda member: (query not in member["display_name"].casefold(), member["display_name"].casefold()))[:limit]


def search_guild_roles(guild_id: str, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    query = query.strip().casefold()
    roles = [{"id": str(role.get("id") or ""), "name": str(role.get("name") or "Role"), "color": int(role.get("color") or 0)} for role in list_guild_roles(guild_id) if not query or query in str(role.get("name") or "").casefold()]
    return sorted(roles, key=lambda role: role["name"].casefold())[:limit]


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
