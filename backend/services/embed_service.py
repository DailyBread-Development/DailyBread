import logging
import re
from typing import Any, Dict, List, Optional

from backend.services import database_service, bible_service
from backend.services import authorization_service
from backend.services.webhook_sender import build_payload_from_embed, send_webhook

LOGGER = logging.getLogger(__name__)


def _payload_for_destination(payload: Dict[str, Any], guild_id: str, role_mentions: Any) -> Dict[str, Any]:
    """Keep selected role IDs scoped to their originating Discord guild."""
    selected = {
        str(item.get("id")): item
        for item in (role_mentions if isinstance(role_mentions, list) else [])
        if isinstance(item, dict) and item.get("type") == "role" and item.get("id")
    }
    if not selected:
        return payload

    import copy
    safe_payload = copy.deepcopy(payload)
    pattern = re.compile(r"<@&(\d+)>")

    def sanitize(value: Any) -> Any:
        if isinstance(value, str):
            def replace(match: re.Match[str]) -> str:
                role = selected.get(match.group(1))
                if not role or str(role.get("guild_id")) == guild_id:
                    return match.group(0)
                return f"@{role.get('role_name') or 'role'}"

            return pattern.sub(replace, value)
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(safe_payload)


# Embed Payload Builder - constructs the JSON payload to send to Discord webhooks based on the embed data and optional Bible verse information.
def create_embed_for_user(
    user_discord_id: str,
    title: str,
    description: str,
    color: Optional[int] = None,
    footer: Optional[str] = None,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    user = database_service.upsert_user_by_discord_id(user_discord_id)
    embed = database_service.create_embed(
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
    embed = database_service.get_embed_by_id(embed_id)
    if not embed:
        return None
    if str(embed.get("creator_id")) != str(database_service.get_user_id_by_discord_id(user_discord_id)):
        return None
    return embed


# Lists all embeds created by the specified user, identified by their Discord ID. Returns a list of embed data dictionaries.
def list_embeds_for_user(user_discord_id: str) -> List[Dict[str, Any]]:
    user_id = database_service.get_user_id_by_discord_id(user_discord_id)
    if not user_id:
        return []
    return database_service.list_embeds_for_user(user_id)


# Sends an embed to the specified Discord webhook, channel, or guild. Validates that the embed belongs to the user and that the user has permission to send to the target. Returns a success status and any error messages.
async def send_embed(
    embed_id: str,
    user_discord_id: str,
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    webhook_id: Optional[str] = None,
) -> Dict[str, Any]:
    embed = database_service.get_embed_by_id(embed_id)
    if not embed:
        return {"success": False, "error": "Embed not found."}

    user_id = database_service.get_user_id_by_discord_id(user_discord_id)
    if not user_id or str(embed.get("creator_id")) != str(user_id):
        return {"success": False, "error": "Only the embed creator may send this embed."}

    if not guild_id and not channel_id and not webhook_id:
        return {"success": False, "error": "guild_id, channel_id, or webhook_id is required to send an embed."}

    webhooks = []
    if webhook_id:
        webhook = database_service.get_webhook_by_id(webhook_id)
        if webhook:
            webhooks = [webhook]
    elif channel_id:
        webhooks = database_service.get_webhooks_for_channel(channel_id)
    elif guild_id:
        webhooks = database_service.get_webhooks_for_guild(guild_id)

    if not webhooks:
        return {"success": False, "error": "No webhook found for the selected gateway."}

    authorized_webhooks = []
    for webhook in webhooks:
        target_guild_id = str(webhook.get("guild_discord_id") or "")
        target_channel_id = str(webhook.get("channel_discord_id") or "")
        if not target_guild_id or not target_channel_id:
            continue
        if guild_id and target_guild_id != str(guild_id):
            if webhook_id:
                return {"success": False, "error": "Selected webhook does not belong to the requested guild."}
            continue
        if channel_id and target_channel_id != str(channel_id):
            if webhook_id:
                return {"success": False, "error": "Selected webhook does not belong to the requested channel."}
            continue

        guild = database_service.get_guild_by_discord_id(target_guild_id)
        channel = database_service.get_channel_for_guild(target_channel_id, target_guild_id)
        if guild and channel and authorization_service.can_send_embed({"id": user_id}, guild, channel):
            authorized_webhooks.append(webhook)

    if not authorized_webhooks:
        return {"success": False, "error": "You do not have permission to send to this channel."}
    webhooks = authorized_webhooks

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
        database_service.audit("embed.sent" if result["success"] else "embed.send_failed", guild_uuid=webhook["guild_id"], user_uuid=user_id, metadata={"embed_id": embed_id, "webhook_id": webhook["discord_id"], "status_code": result.get("status_code")})
        results.append(result)

    all_success = all(item.get("success") for item in results)
    if all_success:
        return {"success": True, "message": "Embed sent successfully.", "results": results}

    return {"success": False, "error": "Webhook delivery failed.", "results": results}


async def send_embed_to_destinations(
    embed_id: str,
    user_discord_id: str,
    destinations: List[Dict[str, str]],
    role_mentions: Any = None,
) -> Dict[str, Any]:
    """Deliver one saved embed to independently validated channel destinations."""
    embed = database_service.get_embed_by_id(embed_id)
    user_id = database_service.get_user_id_by_discord_id(user_discord_id)
    if not embed:
        return {"success": False, "error": "Embed not found."}
    if not user_id or str(embed.get("creator_id")) != str(user_id):
        return {"success": False, "error": "Only the embed creator may send this embed."}

    bible_data = None
    if embed.get("verse_reference"):
        try:
            bible_data = bible_service.resolve_verse_reference(str(embed["verse_reference"]))
        except Exception:
            bible_data = None
    payload = build_payload_from_embed(embed, bible_data)

    results: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    LOGGER.info("Mass send starting embed_id=%s destination_count=%s", embed_id, len(destinations))
    for destination in destinations:
        guild_id = str(destination.get("guild_id") or "").strip()
        channel_id = str(destination.get("channel_id") or "").strip()
        key = (guild_id, channel_id)
        if key in seen:
            continue
        seen.add(key)

        outcome: Dict[str, Any] = {"guild_id": guild_id, "channel_id": channel_id, "success": False}
        LOGGER.info("Mass send destination guild_id=%s channel_id=%s", guild_id, channel_id)
        try:
            if not guild_id or not channel_id:
                outcome["error"] = "Destination is missing a guild or channel ID."
            elif not (guild := database_service.get_guild_by_discord_id(guild_id)) or not guild.get("has_bot"):
                outcome["error"] = "DailyBread is not installed in this server."
            else:
                channel = database_service.get_channel_for_guild(channel_id, guild_id)
                channel_type = channel.get("channel_type") if channel else None
                if not channel or int(channel_type) != 0:
                    outcome["error"] = "Channel is not a valid text destination in this server."
                elif not authorization_service.can_send_embed({"id": user_id}, guild, channel):
                    outcome["error"] = "You do not have permission to send to this channel."
                else:
                    webhooks = database_service.get_webhooks_for_channel(channel_id)
                    webhook = next((item for item in webhooks if str(item.get("guild_discord_id")) == guild_id), None)
                    if not webhook:
                        outcome["error"] = "No DailyBread webhook is configured for this channel."
                    else:
                        delivery = await send_webhook(webhook, _payload_for_destination(payload, guild_id, role_mentions))
                        outcome.update({"success": bool(delivery.get("success")), "error": delivery.get("error")})
                        database_service.audit(
                            "embed.sent" if outcome["success"] else "embed.send_failed",
                            guild_uuid=webhook["guild_id"], user_uuid=user_id,
                            metadata={"embed_id": embed_id, "webhook_id": webhook["discord_id"], "status_code": delivery.get("status_code")},
                        )
        except (TypeError, ValueError):
            outcome["error"] = "Channel data is invalid for this destination."
        except Exception:  # noqa: BLE001
            LOGGER.exception("Mass send destination processing failed guild_id=%s channel_id=%s", guild_id, channel_id)
            outcome["error"] = "Unable to process this destination."

        if outcome["success"]:
            LOGGER.info("Mass send destination succeeded guild_id=%s channel_id=%s", guild_id, channel_id)
        else:
            LOGGER.warning(
                "Mass send destination failed guild_id=%s channel_id=%s error=%s",
                guild_id, channel_id, outcome.get("error", "Unknown send failure"),
            )
        results.append(outcome)

    succeeded = sum(item["success"] for item in results)
    return {
        "success": succeeded > 0,
        "total_destinations": len(results),
        "successful_sends": succeeded,
        "failed_sends": len(results) - succeeded,
        "results": results,
    }
