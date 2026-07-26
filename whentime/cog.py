import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from redbot.core import Config, checks, commands

from .parser import find_time

IDENTIFIER = 724689030408665012
log = logging.getLogger("red.cog.when")


class SetTimestampModal(discord.ui.Modal):
    """Set a timestamp reply to a specific date and time."""

    def __init__(self, view: "TimestampActionsView", timezone_name: str):
        super().__init__(title="Set timestamp")
        self.view = view
        self.timezone_name = timezone_name
        self.value = discord.ui.TextInput(
            label=f"Date and time ({timezone_name})",
            placeholder="YYYY-MM-DD HH:MM",
            required=True,
            max_length=16,
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction):
        timestamp = self.view.cog._parse_timestamp(self.value.value, self.timezone_name)
        if timestamp is None:
            await interaction.response.send_message(
                "Enter a future date and time as `YYYY-MM-DD HH:MM`.",
                ephemeral=True,
            )
            return

        try:
            await self.view.reply.edit(content=f"<t:{int(timestamp.timestamp())}:R>")
        except discord.NotFound:
            await self.view.cog._untrack_reply(
                self.view.guild, self.view.message_id
            )
            message = "That timestamp reply no longer exists."
        except (discord.Forbidden, discord.HTTPException):
            log.warning(
                "Unable to update timestamp reply %s for message %s",
                self.view.reply.id,
                self.view.message_id,
            )
            message = "I could not update that timestamp reply."
        else:
            message = "Timestamp reply updated."

        await interaction.response.send_message(message, ephemeral=True)


class TimestampActionsView(discord.ui.View):
    """Ephemeral actions for a timestamp reply."""

    def __init__(
        self,
        cog: "WhenCog",
        guild: discord.Guild,
        message_id: int,
        reply: discord.Message,
        author_id: int,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.message_id = message_id
        self.reply = reply
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the original poster can manage this timestamp.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Remove reply", style=discord.ButtonStyle.danger)
    async def remove_reply(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        await self.cog._delete_timestamp_reply(
            self.guild, self.message_id, self.reply
        )
        await interaction.followup.send("Timestamp reply removed.", ephemeral=True)

    @discord.ui.button(label="Set timestamp", style=discord.ButtonStyle.primary)
    async def set_timestamp(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        timezone_name = await self.cog.config.guild(self.guild).timezone()
        await interaction.response.send_modal(SetTimestampModal(self, timezone_name))

    @discord.ui.button(label="Never reply", style=discord.ButtonStyle.secondary)
    async def never_reply(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog._set_never_reply(self.guild, self.author_id)
        await interaction.response.send_message(
            "When will no longer reply to your messages in this server.",
            ephemeral=True,
        )


class TimestampControlsView(discord.ui.View):
    """Open private timestamp reply actions for the original poster."""

    def __init__(
        self,
        cog: "WhenCog",
        guild: discord.Guild,
        message_id: int,
        author_id: int,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.message_id = message_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the original poster can manage this timestamp.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Manage timestamp", style=discord.ButtonStyle.secondary)
    async def manage_timestamp(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Manage this timestamp reply:",
            view=TimestampActionsView(
                self.cog,
                self.guild,
                self.message_id,
                interaction.message,
                self.author_id,
            ),
            ephemeral=True,
        )


class WhenCog(commands.Cog):
    """Reply to common time expressions with relative Discord timestamps."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(
            enabled=False,
            enabled_channels=[],
            timestamp_replies={},
            timezone="UTC",
            user_preferences={},
        )

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        """Delete a user's guild-specific reply preferences."""
        for guild_id in (await self.config.all_guilds()).keys():
            guild_config = self.config.guild_from_id(guild_id)
            async with guild_config.user_preferences() as preferences:
                preferences.pop(str(user_id), None)

    async def _track_reply(
        self, guild: discord.Guild, message_id: int, reply_id: int
    ):
        async with self.config.guild(guild).timestamp_replies() as replies:
            replies[str(message_id)] = reply_id

    async def _get_tracked_reply_id(
        self, guild: discord.Guild, message_id: int
    ) -> Optional[int]:
        replies = await self.config.guild(guild).timestamp_replies()
        return replies.get(str(message_id))

    async def _untrack_reply(self, guild: discord.Guild, message_id: int):
        async with self.config.guild(guild).timestamp_replies() as replies:
            replies.pop(str(message_id), None)

    async def _delete_timestamp_reply(
        self, guild: discord.Guild, message_id: int, reply: discord.Message
    ):
        try:
            await reply.delete()
        except discord.NotFound:
            pass
        except (discord.Forbidden, discord.HTTPException):
            log.warning(
                "Unable to delete timestamp reply %s for message %s",
                reply.id,
                message_id,
            )
            return
        await self._untrack_reply(guild, message_id)

    async def _should_reply_to_user(
        self, guild: discord.Guild, user_id: int
    ) -> bool:
        preferences = await self.config.guild(guild).user_preferences()
        preference = preferences.get(str(user_id), {})
        return not preference.get("never_reply", False)

    async def _set_never_reply(self, guild: discord.Guild, user_id: int):
        async with self.config.guild(guild).user_preferences() as preferences:
            preferences[str(user_id)] = {"never_reply": True}

    @staticmethod
    def _parse_timestamp(value: str, timezone_name: str) -> Optional[datetime]:
        try:
            timestamp = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo(timezone_name)
            )
        except (ValueError, ZoneInfoNotFoundError):
            return None
        if timestamp <= datetime.now(timezone.utc):
            return None
        return timestamp.astimezone(timezone.utc)

    async def _fetch_tracked_reply(
        self, message: discord.Message, reply_id: int
    ) -> Optional[discord.Message]:
        try:
            return await message.channel.fetch_message(reply_id)
        except discord.NotFound:
            await self._untrack_reply(message.guild, message.id)
        except (discord.Forbidden, discord.HTTPException):
            log.warning(
                "Unable to fetch timestamp reply %s for message %s",
                reply_id,
                message.id,
            )
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Reply when an enabled channel contains a supported time expression."""
        if message.guild is None or message.author.bot or not message.content:
            return

        guild_config = self.config.guild(message.guild)
        enabled = await guild_config.enabled()
        enabled_channels = await guild_config.enabled_channels()
        if not enabled and message.channel.id not in enabled_channels:
            return

        if not await self._should_reply_to_user(message.guild, message.author.id):
            return

        timezone_name = await guild_config.timezone()
        try:
            guild_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            guild_timezone = timezone.utc

        timestamp = find_time(
            message.content,
            message.created_at.astimezone(guild_timezone),
        )
        if timestamp is not None:
            reply = await message.reply(
                f"<t:{int(timestamp.timestamp())}:R>",
                allowed_mentions=discord.AllowedMentions.none(),
                view=TimestampControlsView(
                    self, message.guild, message.id, message.author.id
                ),
            )
            await self._track_reply(message.guild, message.id, reply.id)

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ):
        """Keep a tracked timestamp reply in sync with an edited message."""
        if after.guild is None or after.author.bot:
            return

        reply_id = await self._get_tracked_reply_id(after.guild, after.id)
        if reply_id is None:
            return

        reply = await self._fetch_tracked_reply(after, reply_id)
        if reply is None:
            return

        timezone_name = await self.config.guild(after.guild).timezone()
        try:
            guild_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            guild_timezone = timezone.utc

        timestamp = find_time(
            after.content,
            (after.edited_at or after.created_at).astimezone(guild_timezone),
        )
        if timestamp is None:
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                log.warning(
                    "Unable to delete timestamp reply %s for message %s",
                    reply_id,
                    after.id,
                )
                return
            await self._untrack_reply(after.guild, after.id)
            return

        try:
            await reply.edit(content=f"<t:{int(timestamp.timestamp())}:R>")
        except discord.NotFound:
            await self._untrack_reply(after.guild, after.id)
        except (discord.Forbidden, discord.HTTPException):
            log.warning(
                "Unable to update timestamp reply %s for message %s",
                reply_id,
                after.id,
            )

    @commands.hybrid_group(name="when")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def when(self, ctx):
        """Configure automatic Discord timestamp replies."""

    @when.command(name="status")
    async def status(self, ctx):
        """Show the current When configuration."""
        config = await self.config.guild(ctx.guild).all()
        channels = [
            channel.mention
            for channel_id in config["enabled_channels"]
            if (channel := ctx.guild.get_channel(channel_id)) is not None
        ]
        scope = "all channels" if config["enabled"] else ", ".join(channels) or "none"
        await ctx.send(
            f"When is enabled in: {scope}. Timezone: `{config['timezone']}`."
        )

    @when.command(name="on")
    async def enable_guild(self, ctx):
        """Enable When in every channel in this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("When is now enabled in every channel.")

    @when.command(name="off")
    async def disable_guild(self, ctx):
        """Disable server-wide When replies; enabled channels stay enabled."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("When is now disabled server-wide.")

    @when.group(name="channel")
    async def channel(self, ctx):
        """Configure individual channels."""

    @channel.command(name="on")
    async def enable_channel(
        self, ctx, channel: Optional[discord.TextChannel] = None
    ):
        """Enable When in one channel."""
        channel = channel or ctx.channel
        enabled_channels = await self.config.guild(ctx.guild).enabled_channels()
        if channel.id in enabled_channels:
            await ctx.send(f"When is already enabled in {channel.mention}.")
            return
        enabled_channels.append(channel.id)
        await self.config.guild(ctx.guild).enabled_channels.set(enabled_channels)
        await ctx.send(f"When is now enabled in {channel.mention}.")

    @channel.command(name="off")
    async def disable_channel(
        self, ctx, channel: Optional[discord.TextChannel] = None
    ):
        """Disable one channel-specific When setting."""
        channel = channel or ctx.channel
        enabled_channels = await self.config.guild(ctx.guild).enabled_channels()
        if channel.id not in enabled_channels:
            await ctx.send(f"When is already disabled in {channel.mention}.")
            return
        enabled_channels.remove(channel.id)
        await self.config.guild(ctx.guild).enabled_channels.set(enabled_channels)
        await ctx.send(f"When is now disabled in {channel.mention}.")

    @when.command(name="timezone")
    async def set_timezone(self, ctx, *, timezone_name: str):
        """Set the IANA timezone used for weekday and clock expressions."""
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            await ctx.send(
                "That is not a valid IANA timezone, for example `Europe/London`."
            )
            return

        await self.config.guild(ctx.guild).timezone.set(timezone_name)
        await ctx.send(f"When timezone set to `{timezone_name}`.")
