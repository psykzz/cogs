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
        "Cleanup old channel ids that may have been deleted or moved manually outside of the bot"
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()
        new_channels = []
        for channel_id in temp_channels:
            channel = guild.get_channel_or_thread(channel_id)
            if not channel:
                log.info(f"Unable to find channel {channel_id} in guild: {guild.id}")
            else:
                new_channels.append(channel.id)
        if len(new_channels):
            log.info(f"Updating temp_channels with {len(new_channels)} remaining channels")
        await guild_group.emptyvoices.temp_channels.set(new_channels)


    async def try_delete_channel(self, guild: discord.Guild, channel: discord.VoiceChannel, should_keep = False):
        "Check if this channel is empty, and delete it"
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()
        is_temp = channel.id in temp_channels

        log.info(f"Validating channel {channel.mention}, temp: {is_temp}, should_keep: {should_keep}")
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
 

    async def validate_category(self, guild: discord.Guild, category: discord.CategoryChannel):
        """
        When someone joins or leaves a category, delete all the empty temp channels, 
        then check if there are any empty channels and create a spare channel if needed.
        """

        log.info(f"Validating category: {category.mention}")
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()

        public_channels = [c for c in category.voice_channels if c.permissions_for(guild.default_role).view_channel and c.id not in temp_channels]
        empty_public_channels = any(len(channel.members) == 0 for channel in public_channels)
        public_temp_channels = [c for c in category.voice_channels if c.id in temp_channels]
        empty_temp_channels = [channel for channel in public_temp_channels if len(channel.members) == 0]

        # Avoid making changes if there are
        if len(public_channels) == 0:
            log.warning(f"{category.mention} doesn't have public channels, not creating anything.")
            return

        if not empty_public_channels:
            # We always keep the first channel.
            for channel in empty_temp_channels[1:]:
                await self.try_delete_channel(guild, channel)
        else:
            # clear all
            for channel in empty_temp_channels:
                await self.try_delete_channel(guild, channel)

        # Refresh the cache
        refreshed_category = await guild.fetch_channel(category.id)
        voice_channels = [c for c in refreshed_category.voice_channels if c.permissions_for(guild.default_role).view_channel]

        # Create a new voice channel if there is no space left in any voice channel
        empty_public_channels = any(len(channel.members) == 0 for channel in voice_channels)
        if not empty_public_channels:
            log.warning(f"I should create a new channel in {category.mention}, it's full...")
            new_voice_channel = await category.create_voice_channel("Voice chat")

            guild_group = self.config.guild(guild)
            temp_channels = await guild_group.emptyvoices.temp_channels()
            await guild_group.emptyvoices.temp_channels.set([*temp_channels, new_voice_channel.id])

        # Cleanup old channels that may no longer exist but we have the id for.
        await self.cleanup_temp_channels_config(guild)
            

    async def try_rename_channel(self, guild, channel: discord.VoiceChannel, member):
        "Attempt to rename a channel that isn't already renamed"
        guild_group = self.config.guild(guild)
        temp_channels = await guild_group.emptyvoices.temp_channels()
        is_temp = channel.id in temp_channels

        # Backwards compat, keep name.
        name = member.name if member else None

        if not is_temp:
            log.info("Not renaming, permanant channel.")
            return
        if 'Voice ' not in channel.name and name:
            log.info("Not renaming, already renamed.")
            return

        new_name = f"{name}'s chat" if name else "Voice chat"

        if member:
            try:
                all_voice_permissions = PermissionOverwrite.from_pair(Permissions.voice(), Permissions.none())
                channel.set_permissions(member, overwrite=all_voice_permissions, reason="EmptyVoices - Giving channel owner permissions.")
            except Exception as e:
                log.warning(f"I dont' have permission to give permission to {member.name}")
        await channel.edit(name=new_name, reason="EmptyVoices - channel renamed")


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        log.info("on_voice_state_update")
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            log.warning("on_voice_state_update - disabled for guild")
            return
        guild = member.guild
        if not guild:
            log.warning("on_voice_state_update - no guild found")
            return

        guild_group = self.config.guild(guild)
        watch_list = await guild_group.emptyvoices.watchlist()
        temp_channels = await guild_group.emptyvoices.temp_channels()

        channels = []
        categories = []
        if before.channel and before.channel.category.id in watch_list:
            log.info(f"Processing watched channel {before.channel.mention}")
            # channels.append(before.channel)
            categories.append(before.channel.category)

            # reset channel name to empty
            if len(before.channel.members) == 0:
                await self.try_rename_channel(guild, before.channel, None)

        if after.channel and after.channel.category.id in watch_list:
            log.info(f"Processing watched channel {after.channel.mention}")
            # channels.append(after.channel)
            categories.append(after.channel.category)

            await self.try_rename_channel(guild, after.channel, member)

        for channel in set(channels):
            await self.try_delete_channel(guild, channel)

        for category in set(categories):
            await self.validate_category(guild, category)

    
    @commands.guild_only()
    @commands.group()
    async def emptyvoices(self, _ctx):
        "Empty Voices"
        pass

        
    @emptyvoices.command()
    async def watching(self, ctx):
        "See what categories are being watched"

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()
        await ctx.send(f"{ctx.author.mention}, We are watching {', '.join(watch_list)}.")

    @emptyvoices.command()
    async def watch(self, ctx, category: discord.CategoryChannel):
        "Set a category to watch"

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()

        # Add current channel to watchlist if not there.
        if category.id not in watch_list:
            watch_list.append(category.id)
            await guild_group.emptyvoices.watchlist.set(watch_list)
            await ctx.send(f"{ctx.author.mention}, adding {category.mention} to watchlist.")
        else:
            await ctx.send(f"{ctx.author.mention}, {category.mention} is already on the watchlist.")

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} channels in the watchlist.")


    @emptyvoices.command()
    async def stopwatch(self, ctx, category: discord.CategoryChannel):
        "Set a category to stop watching"

        guild_group = self.config.guild(ctx.guild)
        watch_list = await guild_group.emptyvoices.watchlist()

        # Remove current channel from watchlist if there.
        if category.id in watch_list:
            watch_list.remove(category.id)
            await guild_group.emptyvoices.watchlist.set(watch_list)
            await ctx.send(f"{ctx.author.mention}, removing {category.mention} from the watchlist.")
        else:
            await ctx.send(f"{ctx.author.mention}, {category.mention} isn't on the watchlist.")

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} channels in the watchlist.")
