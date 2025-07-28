import logging
import discord
from redbot.core import Config, commands


IDENTIFIER = 1672261474290236288

default_guild = {
    "emptyvoices": {
        "watchlist": [],
        "temp_channels": [],
    },
}

log = logging.getLogger("red.cog.empty_voices")


class EmptyVoices(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )

        self.config.register_guild(**default_guild)

    async def cleanup_temp_channels_config(self, guild: discord.Guild):
        """Cleanup old channel ids that may have been deleted or moved
        manually outside of the bot"""
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()
        new_channels = []
        for channel_id in temp_channels:
            channel = guild.get_channel_or_thread(channel_id)
            if not channel:
                log.info(f"Unable to find channel {channel_id} in "
                         f"guild: {guild.id}")
            else:
                new_channels.append(channel.id)
        if len(new_channels):
            log.info(f"Updating temp_channels with {len(new_channels)} "
                     f"remaining channels")
        await guild_group.emptyvoices.temp_channels.set(new_channels)

    async def try_delete_channel(self, guild: discord.Guild,
                                 channel: discord.VoiceChannel,
                                 should_keep=False):
        """Check if this channel is empty, and delete it"""
        try:
            guild_group = self.config.guild(guild)
            temp_channels = await guild_group.emptyvoices.temp_channels()
            is_temp = channel.id in temp_channels

            log.info(f"Validating channel {channel.mention}, temp: {is_temp}"
                     f", should_keep: {should_keep}")
            if should_keep:
                return
            if not is_temp:
                return
            if len(channel.members) > 0:
                return

            log.info(f"I should delete {channel.mention}, it's empty...")
            temp_channels.remove(channel.id)
            await guild_group.emptyvoices.temp_channels.set(temp_channels)
            await channel.delete(reason="Removing empty temp channel")
        except discord.Forbidden:
            log.error(f"Missing permissions to delete channel {channel.name}"
                      f" in guild {guild.name}")
        except discord.NotFound:
            log.warning(f"Channel {channel.name} was already deleted")
            # Remove from temp_channels if it was there
            try:
                guild_group = self.config.guild(guild)
                temp_channels = await \
                    guild_group.emptyvoices.temp_channels()
                if channel.id in temp_channels:
                    temp_channels.remove(channel.id)
                    await guild_group.emptyvoices.temp_channels.set(
                        temp_channels)
            except Exception as e:
                log.error(f"Error cleaning up deleted channel from "
                          f"config: {e}")
        except Exception as e:
            log.error(f"Unexpected error deleting channel {channel.name}: {e}")

    async def validate_category(self, guild: discord.Guild,
                                category: discord.CategoryChannel):
        """When someone joins or leaves a category, delete all the empty temp
        channels, then check if there are any empty channels and create a
        spare channel if needed.
        """

        log.info(f"Validating category: {category.mention}")
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()

        public_channels = [
            c for c in category.voice_channels
            if c.permissions_for(guild.default_role).view_channel
            and c.id not in temp_channels]
        empty_public_channels = any(len(channel.members) == 0
                                    for channel in public_channels)
        public_temp_channels = [c for c in category.voice_channels
                                if c.id in temp_channels]
        empty_temp_channels = [channel for channel in public_temp_channels
                               if len(channel.members) == 0]

        # Avoid making changes if there are no public channels
        if len(public_channels) == 0:
            log.warning(f"{category.mention} doesn't have public channels, "
                        "not creating anything.")
            return

        # If we don't have free public channels then we should keep a voice
        # channel, try to delete all but the first.
        # otherwise, if there is a public channel free, try to remove all the
        # channels.
        if not empty_public_channels:
            # We always keep the first channel.
            for channel in empty_temp_channels[1:]:
                await self.try_delete_channel(guild, channel)
        else:
            # clear all
            for channel in empty_temp_channels:
                await self.try_delete_channel(guild, channel)

        # Since we've deleted some things, we need to refresh the cache and
        # check again.
        try:
            refreshed_category = await guild.fetch_channel(category.id)
            voice_channels = [c for c in refreshed_category.voice_channels
                              if c.permissions_for(
                                  guild.default_role).view_channel]
        except discord.NotFound:
            log.error(f"Category {category.name} not found when refreshing")
            return
        except discord.Forbidden:
            log.error(f"Missing permissions to fetch category "
                      f"{category.name}")
            return
        except Exception as e:
            log.error(f"Error refreshing category {category.name}: {e}")
            return

        # Create a new voice channel if there is no space left in any voice
        # channel
        empty_public_channels = any(len(channel.members) == 0
                                    for channel in voice_channels)
        if not empty_public_channels:
            log.warning(f"I should create a new channel in "
                        f"{category.mention}, it's full...")
            try:
                new_voice_channel = await category.create_voice_channel(
                    "Voice chat")

                guild_group = self.config.guild(guild)
                temp_channels = await \
                    guild_group.emptyvoices.temp_channels()
                await guild_group.emptyvoices.temp_channels.set(
                    [*temp_channels, new_voice_channel.id])
            except discord.Forbidden:
                log.error(f"Missing permissions to create voice channel in "
                          f"category {category.name}")
            except Exception as e:
                log.error(f"Error creating voice channel in category "
                          f"{category.name}: {e}")

        # Cleanup old channels that may no longer exist but we have the id for
        await self.cleanup_temp_channels_config(guild)

    async def try_rename_channel(self, guild, channel: discord.VoiceChannel,
                                 member):
        """Attempt to rename a channel that isn't already renamed"""
        try:
            guild_group = self.config.guild(guild)
            temp_channels = await guild_group.emptyvoices.temp_channels()
            is_temp = channel.id in temp_channels

            # Backwards compat, keep name.
            name = member.name if member else None

            # avoid resetting channels, prefer to delete them.
            if not name:
                return

            if not is_temp:
                log.info("Not renaming, permanent channel.")
                return
            if 'Voice ' not in channel.name and name:
                log.info("Not renaming, already renamed.")
                return

            new_name = f"{name}'s chat" if name else "Voice chat"

            # This is highly rate limited, we should avoid doing this to the
            # same channel too much.
            await channel.edit(name=new_name,
                               reason="EmptyVoices - channel renamed")
        except discord.Forbidden:
            log.error(f"Missing permissions to rename channel "
                      f"{channel.name} in guild {guild.name}")
        except discord.HTTPException as e:
            log.error(f"HTTP error renaming channel {channel.name}: {e}")
        except Exception as e:
            log.error(f"Unexpected error renaming channel {channel.name}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        log.info("on_voice_state_update")
        try:
            if await self.bot.cog_disabled_in_guild(self, member.guild):
                log.warning("on_voice_state_update - disabled for guild")
                return
            guild = member.guild
            if not guild:
                log.warning("on_voice_state_update - no guild found")
                return

            guild_group = self.config.guild(guild)
            watch_list = await guild_group.emptyvoices.watchlist()

            channels = []
            categories = []
            if (before.channel and before.channel.category and
                    before.channel.category.id in watch_list):
                log.info(f"Processing watched channel "
                         f"{before.channel.mention}")
                categories.append(before.channel.category)

                # reset channel name to empty
                if len(before.channel.members) == 0:
                    channels.append(before.channel)

            if (after.channel and after.channel.category and
                    after.channel.category.id in watch_list):
                log.info(f"Processing watched channel "
                         f"{after.channel.mention}")
                categories.append(after.channel.category)

                await self.try_rename_channel(guild, after.channel, member)

            for channel in set(channels):
                await self.try_delete_channel(guild, channel)

            for category in set(categories):
                await self.validate_category(guild, category)
        except Exception as e:
            log.error(f"Error in on_voice_state_update: {e}", exc_info=True)

    @commands.guild_only()
    @commands.group()
    async def emptyvoices(self, _ctx):
        """Empty Voices"""
        pass

    @emptyvoices.command()
    async def cleanup(self, ctx):
        """Manually clean up orphaned temporary channels and config"""

        guild_group = self.config.guild(ctx.guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()
        watch_list = await guild_group.emptyvoices.watchlist()

        if not temp_channels and not watch_list:
            await ctx.send(f"{ctx.author.mention}, Nothing to clean up.")
            return

        # Clean up temp channels
        valid_temp_channels = []
        removed_temp_count = 0

        for channel_id in temp_channels:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                valid_temp_channels.append(channel_id)
            else:
                removed_temp_count += 1

        # Clean up watch list
        valid_watch_list = []
        removed_watch_count = 0

        for category_id in watch_list:
            category = ctx.guild.get_channel(category_id)
            if category and isinstance(category, discord.CategoryChannel):
                valid_watch_list.append(category_id)
            else:
                removed_watch_count += 1

        # Update config
        await guild_group.emptyvoices.temp_channels.set(valid_temp_channels)
        await guild_group.emptyvoices.watchlist.set(valid_watch_list)

        cleanup_msg = f"{ctx.author.mention}, Cleanup complete!\n"
        cleanup_msg += (f"• Removed {removed_temp_count} orphaned temp "
                        f"channels from config\n")
        cleanup_msg += (f"• Removed {removed_watch_count} missing categories "
                        f"from watch list\n")
        cleanup_msg += f"• {len(valid_temp_channels)} temp channels remain\n"
        cleanup_msg += (f"• {len(valid_watch_list)} categories still being "
                        f"watched")

        await ctx.send(cleanup_msg)

    @emptyvoices.command()
    async def list(self, ctx):
        """List current temporary channels"""

        guild_group = self.config.guild(ctx.guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()

        if not temp_channels:
            await ctx.send(f"{ctx.author.mention}, No temporary channels "
                           f"currently exist.")
            return

        channel_info = []
        valid_channels = []

        for channel_id in temp_channels:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                member_count = len(channel.members)
                status = "🔊 Active" if member_count > 0 else "🔇 Empty"
                channel_info.append(f"• {channel.mention} ({member_count} "
                                    f"members) - {status}")
                valid_channels.append(channel_id)
            else:
                channel_info.append(f"• Unknown Channel (ID: {channel_id}) "
                                    f"- ❌ Missing")

        # Update config to remove invalid channels
        if len(valid_channels) != len(temp_channels):
            await guild_group.emptyvoices.temp_channels.set(valid_channels)

        message = (f"{ctx.author.mention}, Current temporary channels:\n" +
                   "\n".join(channel_info))
        await ctx.send(message)

    @emptyvoices.command()
    async def watching(self, ctx):
        """See what categories are being watched"""

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()

        if not watch_list:
            await ctx.send(f"{ctx.author.mention}, No categories are "
                           f"currently being watched.")
            return

        category_names = []
        for category_id in watch_list:
            category = ctx.guild.get_channel(category_id)
            if category:
                category_names.append(category.name)
            else:
                category_names.append(f"Unknown Category (ID: {category_id})")

        await ctx.send(f"{ctx.author.mention}, We are watching: "
                       f"{', '.join(category_names)}")

    @emptyvoices.command()
    async def watch(self, ctx, category: discord.CategoryChannel):
        """Set a category to watch"""

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()

        # Add current channel to watchlist if not there.
        if category.id not in watch_list:
            watch_list.append(category.id)
            await guild_group.emptyvoices.watchlist.set(watch_list)
            await ctx.send(f"{ctx.author.mention}, adding {category.mention} "
                           f"to watchlist.")
        else:
            await ctx.send(f"{ctx.author.mention}, {category.mention} is "
                           f"already on the watchlist.")

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} "
                       f"channels in the watchlist.")

    @emptyvoices.command()
    async def stopwatch(self, ctx, category: discord.CategoryChannel):
        """Set a category to stop watching"""

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()

        # Remove current channel from watchlist if there.
        if category.id in watch_list:
            watch_list.remove(category.id)
            await guild_group.emptyvoices.watchlist.set(watch_list)
            await ctx.send(f"{ctx.author.mention}, removing "
                           f"{category.mention} from the watchlist.")
        else:
            await ctx.send(f"{ctx.author.mention}, {category.mention} isn't "
                           f"on the watchlist.")

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} "
                       f"channels in the watchlist.")
