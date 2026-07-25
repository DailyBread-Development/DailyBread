from __future__ import annotations  # noqa: I001

import discord


MANAGEMENT_PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_webhooks",
)


BOT_PERMISSIONS = discord.Permissions(
    manage_webhooks=True,
    read_messages=True,
    send_messages=True,
    view_channel=True,
)


def user_can_manage(member: discord.Member) -> bool:
    """Check whether a server member can manage DailyBread bot setup."""

    permissions = member.guild_permissions
    return any(getattr(permissions, permission, False) for permission in MANAGEMENT_PERMISSIONS)


async def ensure_management_access(interaction: discord.Interaction) -> bool:
    """Stop a slash command early when the user does not have management access."""

    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This command can only be used inside a Discord server.",
            ephemeral=True,
        )
        return False

    if user_can_manage(interaction.user):
        return True

    await interaction.response.send_message(
        "You need Administrator, Manage Server, or Manage Webhooks permission to manage DailyBread.",
        ephemeral=True,
    )
    return False
