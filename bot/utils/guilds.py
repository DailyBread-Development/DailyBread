"""Discord guild metadata helpers.

The bot intentionally never writes Supabase. Database synchronization occurs only
in the website OAuth login flow for guilds selected by the logging-in user.
"""
from __future__ import annotations

from typing import Any

import discord


def guild_metadata(guild: discord.Guild) -> dict[str, Any]:
    """Return in-memory guild metadata for bot features and diagnostics."""
    return {
        "guild_id": guild.id,
        "name": guild.name,
        "member_count": guild.member_count,
        "channel_count": len(guild.channels),
    }
