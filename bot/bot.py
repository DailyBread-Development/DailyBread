from __future__ import annotations  # noqa: I001

import logging

import discord
from discord.ext import commands

from bot.cogs.dailybread import DailyBreadCog
from bot.events.lifecycle import register_lifecycle_events
from bot.utils.config import configure_logging, get_discord_token, get_runtime_environment, load_environment_variables


load_environment_variables()

LOGGER = logging.getLogger("dailybread.bot")


class DailyBreadBot(commands.Bot):
    """discord.py bot with DailyBread cogs loaded during startup."""

    async def setup_hook(self) -> None:
        await self.add_cog(DailyBreadCog(self))


def create_bot() -> commands.Bot:
    """Create the discord.py bot, register events, and load bot cogs."""

    intents = discord.Intents.default()
    intents.guilds = True

    bot = DailyBreadBot(
        command_prefix="!",
        intents=intents,
        description="DailyBread Discord integration bot",
    )

    register_lifecycle_events(bot)

    return bot


def run_bot() -> None:
    """Bot startup function used by local hosting and Cloudflare Tunnel."""

    configure_logging()
    LOGGER.info("DailyBread environment mode: %s", get_runtime_environment())
    token = get_discord_token()
    bot = create_bot()
    LOGGER.info("Starting DailyBread bot")
    bot.run(token)


if __name__ == "__main__":
    run_bot()
