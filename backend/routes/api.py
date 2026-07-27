from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from backend.auth import build_guild_icon_url, get_session
from backend.services import bible_service, discord_service, supabase_service

api_router = APIRouter()

ADMIN_PERMISSIONS = 0x00000008
MANAGE_WEBHOOKS = 0x02000000


# Error response helper
def _error(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "error": message})


# Session and Guild Helpers
def _get_session(request: Request) -> dict[str, Any] | None:
    session = get_session(request)
    return session if session else None


# Guild Searcher - finds the guild in the session by ID
def _find_guild(session: dict[str, Any], guild_id: str) -> dict[str, Any] | None:
    return next((g for g in session.get("guilds", []) if str(g.get("guild_id")) == str(guild_id)), None)


# Permission Checker - checks if the user has admin or manage_webhooks permissions for the guild
def _require_session(request: Request) -> dict[str, Any]:
    session = _get_session(request)
    if not session:
        raise ValueError("Authentication required")
    return session


# Guild Permission Checker
def _has_guild_permission(guild: dict[str, Any]) -> bool:
    # Guild must be admin or owner (already filtered during OAuth sync)
    return guild.get("is_admin", False) or guild.get("is_owner", False)


# Color Normalizer - converts hex string or integer to integer color value
def _normalize_color(color: Any) -> int | None:
    if color is None:
        return None
    if isinstance(color, int):
        if 0 <= color <= 0xFFFFFF:
            return color
        return None
    value = str(color).strip().lstrip("#")
    if not value:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


# Embed Payload Builder - constructs the Discord embed payload from the input data
def _embed_payload(embed: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "embeds": [
            {
                "title": embed.get("title"),
                "description": embed.get("description"),
                "color": _normalize_color(embed.get("color")) or 0,
            }
        ]
    }
    footer = embed.get("footer")
    if footer:
        payload["embeds"][0]["footer"] = {"text": footer}

    image_url = embed.get("image_url")
    if image_url:
        payload["embeds"][0]["image"] = {"url": image_url}

    message_content = embed.get("message_content")
    if message_content:
        payload["content"] = str(message_content)

    if embed.get("verse_reference") and embed.get("verse_text"):
        payload["embeds"][0]["fields"] = [
            {
                "name": embed["verse_reference"],
                "value": embed["verse_text"],
                "inline": False,
            }
        ]
    return payload


# Sync User and Guilds - ensures the user and their guilds are upserted in the database, and returns the normalized guild data for API responses
def _sync_user_and_guilds(session: dict[str, Any]) -> dict[str, Any]:
    user_profile = session["user"]
    user_record = supabase_service.upsert_user_by_discord_id(
        discord_id=str(user_profile["id"]),
        username=user_profile.get("username", ""),
        avatar=user_profile.get("avatar"),
        global_name=user_profile.get("global_name", ""),
    )

    synced_guilds = []
    for guild in session.get("guilds", []):
        guild_id = str(guild.get("guild_id", ""))
        is_owner = guild.get("is_owner", False)
        is_admin = guild.get("is_admin", False)
        permissions = int(guild.get("permissions", 0) or 0)

        # Bot presence is already in session from OAuth sync
        has_bot = guild.get("has_bot", False)

        db_guild = supabase_service.upsert_guild(
            guild_id=guild_id,
            name=guild.get("name", ""),
            icon=guild.get("icon"),
            owner_id=str(user_record["discord_id"]) if is_owner else None,
            permissions=permissions,
            has_bot=has_bot,
        )

        supabase_service.ensure_user_guild(
            user_id=user_record["id"],
            guild_id=guild_id,
            permissions=permissions,
            is_owner=is_owner,
            is_admin=is_admin,
        )

        # Normalized response format
        synced_guilds.append(
            {
                "guild_id": db_guild["guild_id"],
                "name": db_guild.get("name"),
                "icon": db_guild.get("icon"),
                "icon_url": build_guild_icon_url(db_guild) if db_guild.get("icon") else None,
                "has_bot": has_bot,
                "is_owner": is_owner,
                "is_admin": is_admin,
            }
        )
    return {"user": user_record, "guilds": synced_guilds}




# API Endpoints
# Guild Endpoints - list guilds, list channels, create webhook, list webhooks, delete webhook
@api_router.get("/guilds")
async def get_guilds(request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    user_record = supabase_service.get_user_by_discord_id(str(session["user"]["id"]))
    if not user_record:
        synced = _sync_user_and_guilds(session)
        return {"success": True, "guilds": synced["guilds"]}

    guilds = supabase_service.get_user_guilds(user_record["id"])
    for guild in guilds:
        guild["icon_url"] = build_guild_icon_url({"id": guild.get("guild_id"), "icon": guild.get("icon")})

    return {"success": True, "guilds": guilds}


# Bible Endpoint - search for verse reference and return verse text
@api_router.get("/bible/search")
async def bible_search(query: str | None = None):
    if not query or not query.strip():
        return _error("A search query is required.", status.HTTP_400_BAD_REQUEST)

    try:
        verse = bible_service.resolve_verse_reference(query.strip())
        if not verse:
            return _error("Verse not found.", status.HTTP_404_NOT_FOUND)

        return {
            "success": True,
            "reference": verse.get("reference"),
            "text": verse.get("text"),
            "translation": verse.get("translation"),
            "translation_label": verse.get("translation_label") or verse.get("translation"),
        }
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _error(
            f"{type(exc).__name__}: {exc}",
            status.HTTP_502_BAD_GATEWAY,
        )


# Channel Endpoints - list channels for guild, create webhook for channel
@api_router.get("/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    guild = _find_guild(session, guild_id)
    if not guild:
        return _error("Guild not found in your Discord session.", status.HTTP_403_FORBIDDEN)
    if not _has_guild_permission(guild):
        return _error("Insufficient permissions for this guild.", status.HTTP_403_FORBIDDEN)

    try:
        channels = discord_service.list_guild_channels(guild_id)
    except RuntimeError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)

    text_channels = [
        {
            "id": str(channel["id"]),
            "name": channel.get("name"),
            "type": channel.get("type"),
        }
        for channel in channels
        if channel.get("type") == 0
    ]

    supabase_service.upsert_channels(
        [
            {
                "discord_id": str(channel["id"]),
                "guild_discord_id": guild_id,
                "name": channel.get("name"),
                "channel_type": channel.get("type"),
            }
            for channel in channels
        ]
    )

    return {"success": True, "channels": text_channels}


# Channel Endpoints - create webhook for channel
@api_router.post("/guilds/{guild_id}/channels/{channel_id}/webhook")
async def create_channel_webhook(guild_id: str, channel_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    guild = _find_guild(session, guild_id)
    if not guild:
        return _error("Guild not found in your Discord session.", status.HTTP_403_FORBIDDEN)
    if not _has_guild_permission(guild):
        return _error("Insufficient permissions for this guild.", status.HTTP_403_FORBIDDEN)

    existing = supabase_service.get_webhooks_for_channel(channel_id)
    if existing:
        return _error(
            "A webhook already exists for this channel. Use an existing webhook or create a new channel target.",
            status.HTTP_409_CONFLICT,
        )

    try:
        webhook = discord_service.create_webhook(channel_id)
    except RuntimeError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)

    webhook_record = supabase_service.create_webhook_record(webhook)
    return {
        "success": True,
        "webhook": {
            "id": webhook_record["discord_id"],
            "name": webhook_record.get("name"),
            "channel_id": webhook_record.get("channel_discord_id"),
            "guild_id": webhook_record.get("guild_discord_id"),
        },
    }


# Embeds Endpoint - create embed, list embeds for user, send embed to channel or webhook
@api_router.post("/embeds")
async def create_embed(request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    data = await request.json()
    if not isinstance(data, dict):
        data = {}

    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    verse_reference = str(data.get("verse_reference", "")).strip()
    verse_text = str(data.get("verse_text", "")).strip()
    footer = str(data.get("footer", "")).strip()
    message_content = str(data.get("message_content", "")).strip()
    image_url = str(data.get("image_url", "")).strip()
    color_value = data.get("color")

    if not title and not description and not message_content:
        return _error("Message content, embed title, or embed description is required.", status.HTTP_400_BAD_REQUEST)

    normalized_color = _normalize_color(color_value)
    if color_value is not None and normalized_color is None:
        return _error("Embed color must be a hexadecimal string or integer.", status.HTTP_400_BAD_REQUEST)

    if verse_reference and not verse_text:
        try:
            bible_data = bible_service.resolve_verse_reference(verse_reference)
            verse_text = bible_data.get("text") if bible_data else ""
        except Exception as exc:
            return _error(str(exc), status.HTTP_502_BAD_GATEWAY)

    # Supabase upsert user and embed record
    user_profile = session["user"]
    user_record = supabase_service.upsert_user_by_discord_id(
        discord_id=str(user_profile["id"]),
        username=user_profile.get("username", ""),
        avatar=user_profile.get("avatar", ""),
        global_name=user_profile.get("global_name", ""),
    )

    embed_record = supabase_service.create_embed(
        creator_id=user_record["id"],
        title=title,
        description=description,
        verse_reference=verse_reference or None,
        verse_text=verse_text or None,
        footer=footer or None,
        color=normalized_color,
        message_content=message_content or None,
        image_url=image_url or None,
    )

    return {
        "success": True,
        "embed": embed_record,
        "embed_id": str(embed_record.get("id")),
    }


# List embeds for user
@api_router.get("/guilds/{guild_id}/webhooks")
async def get_guild_webhooks(guild_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    guild = _find_guild(session, guild_id)
    if not guild:
        return _error("Guild not found in your Discord session.", status.HTTP_403_FORBIDDEN)

    try:
        webhooks = supabase_service.get_webhooks_for_guild(guild_id)
    except Exception as exc:
        return _error(str(exc) or "Failed to retrieve webhooks.", status.HTTP_502_BAD_GATEWAY)

    webhook_list = []
    for webhook in webhooks:
        webhook_list.append({
            "id": webhook.get("discord_id"),
            "name": webhook.get("name"),
            "channel_id": webhook.get("channel_discord_id"),
            "channel_name": webhook.get("channel_name"),
            "guild_id": webhook.get("guild_discord_id"),
            "created_at": webhook.get("created_at"),
        })

    return {"success": True, "webhooks": webhook_list}


# Delete webhook
@api_router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    webhook = supabase_service.get_webhook_by_id(webhook_id)
    if not webhook:
        return _error("Webhook not found.", status.HTTP_404_NOT_FOUND)

    guild_id = webhook.get("guild_discord_id")
    guild = _find_guild(session, guild_id)
    if not guild:
        return _error("Guild not found in your Discord session.", status.HTTP_403_FORBIDDEN)
    if not _has_guild_permission(guild):
        return _error("Insufficient permissions for this guild.", status.HTTP_403_FORBIDDEN)

    try:
        supabase_service.delete_webhook(webhook_id)
        return {"success": True, "message": "Webhook deleted successfully."}
    except Exception as exc:
        return _error(str(exc) or "Failed to delete webhook.", status.HTTP_502_BAD_GATEWAY)

