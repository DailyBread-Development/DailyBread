from __future__ import annotations  # noqa: I001

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.errors import DailyBreadPermissionError
from bot.utils.guilds import cleanup_channel, cleanup_guild, sync_guild


LOGGER = logging.getLogger("dailybread.bot")


def register_lifecycle_events(bot: commands.Bot) -> None:
    """Register Discord lifecycle and error events."""

    @bot.event
    async def on_ready() -> None:
        guilds = list(bot.guilds)
        LOGGER.info("DailyBread bot logged in as %s guilds=%s", bot.user, len(guilds))

        if not getattr(bot, "dailybread_commands_synced", False):
            synced_commands = await bot.tree.sync()
            bot.dailybread_commands_synced = True
            LOGGER.info("Synced Discord application commands count=%s", len(synced_commands))

        for guild in guilds:
            await sync_guild(guild)

    @bot.event
    async def on_guild_join(guild: discord.Guild) -> None:
        LOGGER.info("Joined guild guild_id=%s name=%s", guild.id, guild.name)
        await sync_guild(guild)

    @bot.event
    async def on_guild_remove(guild: discord.Guild) -> None:
        LOGGER.info("Removed from guild guild_id=%s name=%s", guild.id, guild.name)
        await cleanup_guild(guild)

    @bot.event
    async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
        LOGGER.info(
            "Channel deleted guild_id=%s channel_id=%s name=%s",
            channel.guild.id,
            channel.id,
            channel.name,
        )
        await cleanup_channel(channel)

    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        LOGGER.exception("Command failed command=%s error=%s", interaction.command, error)

        original_error = getattr(error, "original", error)
        message = "DailyBread could not complete that command. Please check bot permissions and try again."
        if isinstance(original_error, app_commands.MissingPermissions):
            message = "You do not have permission to use that command."
        elif isinstance(original_error, DailyBreadPermissionError):
            message = "DailyBread is missing a required Discord permission in that channel."
        elif isinstance(original_error, discord.Forbidden):
            message = "DailyBread is missing a required Discord permission."
        elif isinstance(original_error, discord.NotFound):
            message = "That Discord resource could not be found."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    bot.tree.on_error = on_app_command_error
