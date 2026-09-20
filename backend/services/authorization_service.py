from __future__ import annotations

from typing import Any

from backend.services import database_service

SEND_EMBEDS = "SEND_EMBEDS"


def _user_id(user: str | dict[str, Any]) -> str:
    if isinstance(user, dict):
        value = user.get("id") or user.get("user_id")
    else:
        value = user
    return str(value or "")


def _guild_id(guild: str | dict[str, Any]) -> str:
    if isinstance(guild, dict):
        value = guild.get("discord_id") or guild.get("guild_id") or guild.get("id")
    else:
        value = guild
    return str(value or "")


def _channel_id(channel: str | dict[str, Any]) -> str:
    if isinstance(channel, dict):
        value = channel.get("discord_id") or channel.get("channel_id") or channel.get("id")
    else:
        value = channel
    return str(value or "")


def _membership(user: str | dict[str, Any], guild: str | dict[str, Any]) -> dict[str, Any] | None:
    user_id = _user_id(user)
    guild_id = _guild_id(guild)
    if not user_id or not guild_id:
        return None
    return database_service.get_guild_membership(user_id, guild_id)


def is_owner(user: str | dict[str, Any], guild: str | dict[str, Any]) -> bool:
    membership = _membership(user, guild)
    return bool(membership and membership.get("is_owner"))


def is_admin(user: str | dict[str, Any], guild: str | dict[str, Any]) -> bool:
    membership = _membership(user, guild)
    return bool(membership and membership.get("is_admin"))


def has_role_permission(user: str | dict[str, Any], guild: str | dict[str, Any], permission: str) -> bool:
    if not _membership(user, guild):
        return False
    return database_service.user_has_role_permission(_user_id(user), _guild_id(guild), permission)


def channel_allows_permission(guild: str | dict[str, Any], channel: str | dict[str, Any], permission: str) -> bool:
    guild_id = _guild_id(guild)
    channel_id = _channel_id(channel)
    if not guild_id or not channel_id:
        return False

    if not database_service.get_channel_for_guild(channel_id, guild_id):
        return False
    return database_service.channel_has_permission(channel_id, guild_id, permission)


def can_send_embed(
    user: str | dict[str, Any],
    guild: str | dict[str, Any],
    channel: str | dict[str, Any],
) -> bool:
    membership = _membership(user, guild)
    if not membership:
        return False

    if membership.get("is_owner") or membership.get("is_admin"):
        return bool(database_service.get_channel_for_guild(_channel_id(channel), _guild_id(guild)))

    return (
        has_role_permission(user, guild, SEND_EMBEDS)
        and channel_allows_permission(guild, channel, SEND_EMBEDS)
    )