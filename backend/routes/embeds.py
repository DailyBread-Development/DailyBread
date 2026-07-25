import json  # noqa: I001
from typing import Any, Dict, Optional  # noqa: F401, UP035

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from backend.auth import get_session
from backend.services import supabase_service
from backend.services.embed_service import create_embed_for_user, get_embed_for_user, list_embeds_for_user, send_embed

router = APIRouter()


# Error response helper
def _error(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "error": message})


# Authentication helper
def _require_session(request: Request) -> Dict[str, Any]:  # noqa: UP006
    session = get_session(request)
    if not session:
        raise ValueError("Authentication required")
    return session


# Permission helper
def _requires_guild_membership(session: Dict[str, Any], guild_id: str) -> bool:  # noqa: UP006
    return any(str(g.get("id")) == str(guild_id) for g in session.get("guilds", []))


# Route handlers for embeds endpoint - create, list, send
@router.post("/")
async def create_embed(request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid JSON payload.", status.HTTP_400_BAD_REQUEST)

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    verse_reference = payload.get("verse_reference")
    color = payload.get("color")
    footer = payload.get("footer")
    message_content = str(payload.get("message_content", "")).strip()
    image_url = str(payload.get("image_url", "")).strip()

    if not title and not description and not message_content:
        return _error("Message content, embed title, or embed description is required.", status.HTTP_400_BAD_REQUEST)

    if color is not None:
        try:
            if isinstance(color, str):
                color = int(color.strip().lstrip("#"), 16)
            elif isinstance(color, float):
                color = int(color)
        except ValueError:
            return _error("Color must be a hex string or integer.", status.HTTP_400_BAD_REQUEST)

    embed = create_embed_for_user(
        user_discord_id=str(session["user"]["id"]),
        title=title,
        description=description,
        verse_reference=str(verse_reference).strip() if verse_reference else None,
        color=color,
        footer=str(footer).strip() if footer else None,
        message_content=message_content or None,
        image_url=image_url or None,
    )

    return {"success": True, "embed_id": str(embed.get("id")), "embed": embed}


# List embeds for the authenticated user - only returns embeds created by the user
@router.get("/")
async def list_embeds(request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    embeds = list_embeds_for_user(str(session["user"]["id"]))
    return {"success": True, "embeds": embeds}


# Get a specific embed by ID, only if it belongs to the authenticated user
@router.get("/{embed_id}")
async def get_embed(embed_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)

    embed = get_embed_for_user(embed_id, str(session["user"]["id"]))
    if not embed:
        return _error("Embed not found or access denied.", status.HTTP_404_NOT_FOUND)

    return {"success": True, "embed": embed}


# Send an embed to a specified guild/channel/webhook - user must have permission to send to the target
@router.post("/{embed_id}/send")
async def send_embed_route(embed_id: str, request: Request):
    try:
        session = _require_session(request)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_401_UNAUTHORIZED)
    
    raw_body = await request.body()
    print("Raw body:", raw_body)
    print("Headers:", request.headers)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return _error("Request body is empty or invalid JSON.", status.HTTP_400_BAD_REQUEST)

    if not isinstance(payload, dict):
        return _error("Invalid JSON payload.", status.HTTP_400_BAD_REQUEST)

    guild_id = str(payload.get("guild_id", "") or "").strip()
    channel_id = str(payload.get("channel_id", "") or "").strip()
    webhook_id = str(payload.get("webhook_id", "") or "").strip() or None

    if not guild_id and not channel_id and not webhook_id:
        return _error("guild_id, channel_id, or webhook_id is required.", status.HTTP_400_BAD_REQUEST)

    embed = supabase_service.get_embed_by_id(embed_id)
    if not embed:
        return _error("Embed not found.", status.HTTP_404_NOT_FOUND)

    user_id = supabase_service.get_user_id_by_discord_id(str(session["user"]["id"]))
    if not user_id or str(embed.get("creator_id")) != str(user_id):
        return _error("Only the embed creator may send this embed.", status.HTTP_403_FORBIDDEN)

    if webhook_id:
        webhook = supabase_service.get_webhook_by_id(webhook_id)
        if not webhook:
            return _error("Webhook not found.", status.HTTP_404_NOT_FOUND)
        if guild_id and str(webhook.get("guild_discord_id")) != guild_id:
            return _error("Selected webhook does not belong to the requested guild.", status.HTTP_400_BAD_REQUEST)
        if not supabase_service.user_has_guild_access(user_id, str(webhook.get("guild_discord_id") or "")):
            return _error("You do not have permission to send to this guild.", status.HTTP_403_FORBIDDEN)

    if channel_id:
        webhooks = supabase_service.get_webhooks_for_channel(channel_id)
        if not webhooks:
            return _error("No webhook found for the selected channel.", status.HTTP_404_NOT_FOUND)
        if not any(supabase_service.user_has_guild_access(user_id, str(wh.get("guild_discord_id") or "")) for wh in webhooks):
            return _error("You do not have permission to send to this channel's guild.", status.HTTP_403_FORBIDDEN)

    if guild_id and not supabase_service.user_has_guild_access(user_id, guild_id):
        return _error("You do not have permission to send to this guild.", status.HTTP_403_FORBIDDEN)

    result = await send_embed(
        embed_id=embed_id,
        user_discord_id=str(session["user"]["id"]),
        guild_id=guild_id or None,
        channel_id=channel_id or None,
        webhook_id=webhook_id,
    )

    if not result.get("success"):
        return _error(result.get("error", "Unable to send embed."), status.HTTP_400_BAD_REQUEST)

    return result
