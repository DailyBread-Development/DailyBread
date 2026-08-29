"""DailyBread v2 Supabase data access.

Every relationship below uses the internal UUID keys defined in supabase/schema.sql.
Discord snowflakes are used only at the application boundary for lookup/upsert.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        load_dotenv(env_path, override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("supabase_url")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("supabase_service_key")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for backend database access.")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
LOGGER = logging.getLogger(__name__)


class SupabaseError(Exception):
    """Raised when Supabase reports a database failure."""


def _execute(query: Any) -> Any:
    result = query.execute()
    if getattr(result, "error", None):
        raise SupabaseError(str(result.error))
    return getattr(result, "data", None)


def get_user_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("users").select("*").eq("discord_id", int(discord_id)).limit(1))
    return rows[0] if rows else None


def get_user_id_by_discord_id(discord_id: str) -> Optional[str]:
    user = get_user_by_discord_id(discord_id)
    return user["id"] if user else None


def upsert_user_by_discord_id(discord_id: str, username: str = "", avatar: str | None = None, global_name: str | None = None) -> dict[str, Any]:
    record = {"discord_id": int(discord_id), "username": username or "Discord user", "avatar": avatar, "global_name": global_name}
    rows = _execute(supabase.table("users").upsert(record, on_conflict="discord_id").select("*") )
    return rows[0]


def store_oauth_session(user_id: str, token_data: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(token_data.get("expires_in", 3600))
    record = {"user_id": user_id, "access_token": token_data["access_token"], "refresh_token": token_data.get("refresh_token"), "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()}
    rows = _execute(supabase.table("oauth_sessions").insert(record).select("*"))
    return rows[0]


def get_latest_oauth_session(user_id: str) -> Optional[dict[str, Any]]:
    """Get the most recent valid OAuth session for a user."""
    rows = _execute(supabase.table("oauth_sessions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(1))
    return rows[0] if rows else None


def get_guild_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("guilds").select("*").eq("discord_id", int(discord_id)).limit(1))
    return rows[0] if rows else None


def upsert_guild(discord_id: str, name: str, icon: str | None = None, owner_discord_id: str | None = None, has_bot: bool = True) -> dict[str, Any]:
    record = {"discord_id": int(discord_id), "name": name or "Unnamed guild", "icon": icon, "owner_discord_id": int(owner_discord_id) if owner_discord_id else None, "has_bot": has_bot}
    rows = _execute(supabase.table("guilds").upsert(record, on_conflict="discord_id").select("*"))
    return rows[0]


def upsert_guild_member(guild_uuid: str, user_uuid: str, is_owner: bool, is_admin: bool) -> dict[str, Any]:
    rows = _execute(supabase.table("guild_members").upsert({"guild_id": guild_uuid, "user_id": user_uuid, "is_owner": is_owner, "is_admin": is_admin}, on_conflict="guild_id,user_id").select("*"))
    return rows[0]


def user_has_guild_access(user_uuid: str, guild_discord_id: str) -> bool:
    guild = get_guild_by_discord_id(guild_discord_id)
    if not guild:
        return False
    rows = _execute(supabase.table("guild_members").select("is_owner,is_admin").eq("guild_id", guild["id"]).eq("user_id", user_uuid).limit(1))
    return bool(rows and (rows[0]["is_owner"] or rows[0]["is_admin"]))


def get_user_guilds(user_uuid: str) -> list[dict[str, Any]]:
    rows = _execute(supabase.table("guild_members").select("is_owner,is_admin,guilds(id,discord_id,name,icon,has_bot,owner_discord_id)").eq("user_id", user_uuid))
    result = []
    for row in rows or []:
        guild = row.get("guilds")
        if not guild:
            continue
        result.append({"id": str(guild["discord_id"]), "guild_id": str(guild["discord_id"]), "name": guild["name"], "icon": guild.get("icon"), "has_bot": guild["has_bot"], "is_owner": row["is_owner"], "is_admin": row["is_admin"], "owner_id": str(guild["owner_discord_id"]) if guild.get("owner_discord_id") else None})
    return result


def upsert_channels(guild_discord_id: str, channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    if not guild:
        raise SupabaseError("Guild has not yet been synchronized by the DailyBread bot.")
    records = [{"guild_id": guild["id"], "discord_id": int(channel["discord_id"]), "name": channel.get("name") or "unnamed", "channel_type": int(channel.get("channel_type", 0)), "position": int(channel.get("position", 0)), "category_id": int(channel["category_id"]) if channel.get("category_id") else None, "nsfw": bool(channel.get("nsfw", False))} for channel in channels]
    return _execute(supabase.table("channels").upsert(records, on_conflict="discord_id").select("*")) if records else []


def get_channel_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("channels").select("*").eq("discord_id", int(discord_id)).limit(1))
    return rows[0] if rows else None


def upsert_roles(guild_discord_id: str, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    if not guild:
        raise SupabaseError("Guild must exist before roles can be synchronized.")
    records = [{"guild_id": guild["id"], "discord_role_id": int(role["discord_role_id"]), "name": role["name"], "color": int(role.get("color", 0)), "position": int(role.get("position", 0)), "permissions": int(role.get("permissions", 0))} for role in roles]
    return _execute(supabase.table("roles").upsert(records, on_conflict="guild_id,discord_role_id").select("*")) if records else []


def replace_member_roles(guild_member_id: str, role_ids: list[str]) -> None:
    _execute(supabase.table("member_roles").delete().eq("guild_member_id", guild_member_id))
    if role_ids:
        _execute(supabase.table("member_roles").insert([{"guild_member_id": guild_member_id, "role_id": role_id} for role_id in role_ids]))


def create_embed(
    creator_id: str,
    title: str,
    description: str,
    color: int | None = None,
    footer: str | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
    author: str | None = None,
    message_content: str | None = None,
    verse_reference: str | None = None,
) -> dict[str, Any]:
    record = {
        "creator_id": creator_id,
        "title": title or None,
        "description": description or None,
        "color": color,
        "footer": footer,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "author": author,
        "message_content": message_content,
        "verse_reference": verse_reference,
    }
    rows = _execute(supabase.table("embeds").insert(record).select("*"))
    return rows[0]


def get_embed_by_id(embed_id: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("embeds").select("*").eq("id", embed_id).limit(1))
    return rows[0] if rows else None


def list_embeds_for_user(user_uuid: str) -> list[dict[str, Any]]:
    return _execute(supabase.table("embeds").select("*").eq("creator_id", user_uuid).order("created_at", desc=True)) or []


def create_container(creator_id: str, name: str, data: dict[str, Any], guild_discord_id: str | None = None) -> dict[str, Any]:
    rows = _execute(supabase.table("containers").insert({"creator_id": creator_id, "name": name or "Untitled container", "data": data}).select("*"))
    container = rows[0]
    if guild_discord_id:
        guild = get_guild_by_discord_id(guild_discord_id)
        if not guild:
            raise SupabaseError("The selected guild has not been synchronized by the bot.")
        _execute(supabase.table("guild_containers").upsert({"guild_id": guild["id"], "container_id": container["id"]}, on_conflict="guild_id,container_id"))
    return container


def list_containers_for_user(user_uuid: str) -> list[dict[str, Any]]:
    return _execute(supabase.table("containers").select("*,guild_containers(guilds(discord_id))").eq("creator_id", user_uuid).order("created_at", desc=True)) or []


def get_container_for_user(container_id: str, user_uuid: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("containers").select("*,guild_containers(guilds(discord_id))").eq("id", container_id).eq("creator_id", user_uuid).limit(1))
    return rows[0] if rows else None


def create_webhook_record(webhook: dict[str, Any]) -> dict[str, Any]:
    guild = get_guild_by_discord_id(str(webhook["guild_id"]))
    channel = get_channel_by_discord_id(str(webhook["channel_id"]))
    if not guild or not channel or channel["guild_id"] != guild["id"]:
        raise SupabaseError("Webhook target is not synchronized by the bot.")
    record = {"guild_id": guild["id"], "channel_id": channel["id"], "discord_webhook_id": int(webhook["id"]), "token": webhook["token"], "name": webhook.get("name") or "DailyBread", "enabled": True}
    rows = _execute(supabase.table("webhooks").upsert(record, on_conflict="discord_webhook_id").select("*"))
    return rows[0]


def _webhook_rows(filter_column: str, value: Any) -> list[dict[str, Any]]:
    return _execute(supabase.table("webhooks").select("*,channels(discord_id,name),guilds(discord_id)").eq(filter_column, value).eq("enabled", True)) or []


def _present_webhook(row: dict[str, Any]) -> dict[str, Any]:
    channel, guild = row.get("channels") or {}, row.get("guilds") or {}
    row["discord_id"] = str(row["discord_webhook_id"]); row["channel_discord_id"] = str(channel.get("discord_id", "")); row["guild_discord_id"] = str(guild.get("discord_id", "")); row["channel_name"] = channel.get("name")
    return row


def get_webhook_by_id(webhook_discord_id: str) -> Optional[dict[str, Any]]:
    rows = _webhook_rows("discord_webhook_id", int(webhook_discord_id))
    return _present_webhook(rows[0]) if rows else None


def get_webhooks_for_channel(channel_discord_id: str) -> list[dict[str, Any]]:
    channel = get_channel_by_discord_id(channel_discord_id)
    return [_present_webhook(row) for row in _webhook_rows("channel_id", channel["id"])] if channel else []


def get_webhooks_for_guild(guild_discord_id: str) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    return [_present_webhook(row) for row in _webhook_rows("guild_id", guild["id"])] if guild else []


def delete_webhook(webhook_discord_id: str) -> None:
    _execute(supabase.table("webhooks").delete().eq("discord_webhook_id", int(webhook_discord_id)))


def audit(action: str, guild_uuid: str | None = None, user_uuid: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    _execute(supabase.table("audit_logs").insert({"action": action, "guild_id": guild_uuid, "user_id": user_uuid, "metadata": metadata or {}}))


# bible_cache deliberately remains byte-for-byte compatible with the prior database.
def get_bible_cache(cache_key: str) -> Optional[dict[str, Any]]:
    rows = _execute(supabase.table("bible_cache").select("*").eq("cache_key", cache_key).limit(1))
    return rows[0] if rows else None


def store_bible_cache(cache_key: str, reference: str, text: str, translation: str | None = None) -> dict[str, Any]:
    rows = _execute(supabase.table("bible_cache").upsert({"cache_key": cache_key, "reference": reference, "text": text, "translation": translation}, on_conflict="cache_key").select("*"))
    return rows[0]
