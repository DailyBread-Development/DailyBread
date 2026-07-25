from __future__ import annotations  # noqa: I001

import logging

import discord

from bot.utils.errors import DailyBreadPermissionError
from bot.utils.models import ChannelMetadata, WebhookMetadata


LOGGER = logging.getLogger("dailybread.bot")


def bot_has_channel_access(channel: discord.TextChannel) -> bool:
    """Check whether the bot can view a channel and manage webhooks there."""

    member = channel.guild.me
    if member is None:
        return False

    permissions = channel.permissions_for(member)
    return permissions.view_channel and permissions.manage_webhooks


def build_channel_metadata(channel: discord.TextChannel) -> ChannelMetadata:
    """Convert a Discord channel into a small metadata object for future sync."""

    member = channel.guild.me
    permissions = channel.permissions_for(member) if member else discord.Permissions.none()
    return ChannelMetadata(
        id=channel.id,
        name=channel.name,
        guild_id=channel.guild.id,
        position=channel.position,
        category_id=channel.category_id,
        bot_can_view=permissions.view_channel,
        bot_can_manage_webhooks=permissions.manage_webhooks,
        bot_can_send_messages=permissions.send_messages,
    )


def list_accessible_text_channels(guild: discord.Guild) -> list[ChannelMetadata]:
    """Return text channels where DailyBread can create and manage webhooks."""

    channels: list[ChannelMetadata] = []

    for channel in guild.text_channels:
        metadata = build_channel_metadata(channel)
        if metadata.bot_can_view and metadata.bot_can_manage_webhooks:
            channels.append(metadata)

    return channels


async def fetch_existing_webhooks(channel: discord.TextChannel) -> list[WebhookMetadata]:
    """Fetch existing webhooks in a channel and normalize them for future storage."""

    if not bot_has_channel_access(channel):
        raise DailyBreadPermissionError("Bot cannot manage webhooks in this channel.")

    webhooks = await channel.webhooks()
    bot_user_id = channel.guild.me.id if channel.guild.me else None
    return [
        WebhookMetadata(
            id=webhook.id,
            name=webhook.name or "Unnamed webhook",
            guild_id=channel.guild.id,
            channel_id=channel.id,
            url=webhook.url,
            created_by_bot=bool(webhook.user and webhook.user.id == bot_user_id),
        )
        for webhook in webhooks
    ]


async def create_webhook(channel: discord.TextChannel, name: str = "DailyBread") -> WebhookMetadata:
    """Create a DailyBread webhook in a channel and return structured metadata."""

    if not bot_has_channel_access(channel):
        raise DailyBreadPermissionError("Bot cannot manage webhooks in this channel.")

    webhook = await channel.create_webhook(
        name=name,
        reason="DailyBread webhook setup",
    )
    LOGGER.info(
        "Created webhook guild_id=%s channel_id=%s webhook_id=%s",
        channel.guild.id,
        channel.id,
        webhook.id,
    )

    return WebhookMetadata(
        id=webhook.id,
        name=webhook.name or name,
        guild_id=channel.guild.id,
        channel_id=channel.id,
        url=webhook.url,
        created_by_bot=True,
    )


async def delete_webhook(webhook: discord.Webhook, reason: str = "DailyBread webhook cleanup") -> None:
    """Delete a Discord webhook object."""

    await webhook.delete(reason=reason)
    LOGGER.info("Deleted webhook webhook_id=%s", webhook.id)


async def delete_webhook_by_id(channel: discord.TextChannel, webhook_id: int) -> bool:
    """Delete a webhook from a channel by ID. Returns True when one was found."""

    webhooks = await channel.webhooks()

    for webhook in webhooks:
        if webhook.id == webhook_id:
            await delete_webhook(webhook)
            return True

    return False


async def validate_webhook(channel: discord.TextChannel, webhook_id: int) -> bool:
    """Confirm that a saved webhook ID still exists in the expected channel."""

    webhooks = await channel.webhooks()
    return any(webhook.id == webhook_id for webhook in webhooks)
