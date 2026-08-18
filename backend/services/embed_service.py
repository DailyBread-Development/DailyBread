from typing import Any, Dict, List, Optional

from backend.services import supabase_service, bible_service
from backend.services.webhook_sender import build_payload_from_embed, send_webhook


# Embed Payload Builder - constructs the JSON payload to send to Discord webhooks based on the embed data and optional Bible verse information.
def create_embed_for_user(
    user_discord_id: str,
    title: str,
    description: str,
    color: Optional[int] = None,
    footer: Optional[str] = None,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    user = supabase_service.upsert_user_by_discord_id(user_discord_id)
    embed = supabase_service.create_embed(
        creator_id=user["id"],
        title=title,
        description=description,
        color=color,
        footer=footer,
        image_url=image_url,
    )
    return embed


# Retrieves an embed by its ID and verifies that it belongs to the specified user. Returns the embed data if found and authorized, or None otherwise.
def get_embed_for_user(embed_id: str, user_discord_id: str) -> Optional[Dict[str, Any]]:
    embed = supabase_service.get_embed_by_id(embed_id)
    if not embed:
        return None
    if str(embed.get("creator_id")) != str(supabase_service.get_user_id_by_discord_id(user_discord_id)):
        return None
    return embed


# Lists all embeds created by the specified user, identified by their Discord ID. Returns a list of embed data dictionaries.
def list_embeds_for_user(user_discord_id: str) -> List[Dict[str, Any]]:
    user_id = supabase_service.get_user_id_by_discord_id(user_discord_id)
    if not user_id:
        return []
    return supabase_service.list_embeds_for_user(user_id)


# Sends an embed to the specified Discord webhook, channel, or guild. Validates that the embed belongs to the user and that the user has permission to send to the target. Returns a success status and any error messages.
async def send_embed(
    embed_id: str,
    user_discord_id: str,
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    webhook_id: Optional[str] = None,
) -> Dict[str, Any]:
    embed = supabase_service.get_embed_by_id(embed_id)
    if not embed:
        return {"success": False, "error": "Embed not found."}

    user_id = supabase_service.get_user_id_by_discord_id(user_discord_id)
    if not user_id or str(embed.get("creator_id")) != str(user_id):
        return {"success": False, "error": "Only the embed creator may send this embed."}

    if not guild_id and not channel_id and not webhook_id:
        return {"success": False, "error": "guild_id, channel_id, or webhook_id is required to send an embed."}

    webhooks = []
    if webhook_id:
        webhook = supabase_service.get_webhook_by_id(webhook_id)
        if webhook:
            webhooks = [webhook]
    elif channel_id:
        webhooks = supabase_service.get_webhooks_for_channel(channel_id)
    elif guild_id:
        webhooks = supabase_service.get_webhooks_for_guild(guild_id)

    if not webhooks:
        return {"success": False, "error": "No webhook found for the selected gateway."}

    # Ensure the user has valid ownership/admin access for the send target.
    user_id = supabase_service.get_user_id_by_discord_id(user_discord_id)
    if not user_id:
        return {"success": False, "error": "Unable to validate user authorization."}

    target_guild_id = str(guild_id or webhooks[0].get("guild_discord_id") or "")
    if not target_guild_id:
        return {"success": False, "error": "Unable to determine target guild for webhook delivery."}

    if not supabase_service.user_has_guild_access(user_id, target_guild_id):
        return {"success": False, "error": "You do not have permission to send to this guild."}

    if webhook_id and str(webhooks[0].get("guild_discord_id")) != target_guild_id:
        return {"success": False, "error": "Selected webhook does not belong to the requested guild."}

    if channel_id and any(str(webhook.get("channel_discord_id")) != str(channel_id) for webhook in webhooks):
        return {"success": False, "error": "Selected webhook does not belong to the requested channel."}

    bible_data = None
    if embed.get("verse_reference"):
        try:
            bible_data = bible_service.resolve_verse_reference(str(embed.get("verse_reference")))
        except Exception:
            bible_data = None

    payload = build_payload_from_embed(embed, bible_data)
    results: List[Dict[str, Any]] = []
    for webhook in webhooks:
        result = await send_webhook(webhook, payload)
        supabase_service.audit("embed.sent" if result["success"] else "embed.send_failed", guild_uuid=webhook["guild_id"], user_uuid=user_id, metadata={"embed_id": embed_id, "webhook_id": webhook["discord_id"], "status_code": result.get("status_code")})
        results.append(result)

    all_success = all(item.get("success") for item in results)
    if all_success:
        return {"success": True, "message": "Embed sent successfully.", "results": results}

    return {"success": False, "error": "Webhook delivery failed.", "results": results}
