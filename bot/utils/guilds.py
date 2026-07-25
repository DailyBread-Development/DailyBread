from __future__ import annotations  # noqa: I001

import logging
from dataclasses import asdict
from typing import Any

import discord

from bot.utils.webhooks import list_accessible_text_channels


LOGGER = logging.getLogger("dailybread.bot")


async def sync_guild(guild: discord.Guild) -> dict[str, Any]:
    """Build the guild payload that a future database sync can store."""

    accessible_channels = list_accessible_text_channels(guild)
    payload = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "member_count": guild.member_count,
        "accessible_channels": [asdict(channel) for channel in accessible_channels],
    }
    LOGGER.info(
        "Synced guild guild_id=%s name=%s accessible_channels=%s",
        guild.id,
        guild.name,
        len(accessible_channels),
    )
    return payload


async def cleanup_guild(guild: discord.Guild) -> None:
    """Placeholder for future database cleanup when the bot leaves a server."""

    LOGGER.info("Prepared guild cleanup guild_id=%s name=%s", guild.id, guild.name)


async def cleanup_channel(channel: discord.abc.GuildChannel) -> None:
    """Placeholder for future database cleanup when a tracked channel is deleted."""

    LOGGER.info(
        "Prepared channel cleanup guild_id=%s channel_id=%s",
        channel.guild.id,
        channel.id,
    )
