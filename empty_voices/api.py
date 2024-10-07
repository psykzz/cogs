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


    async def validate_channel(guild: discord.Guild, channel: discord.VoiceChannel):
        "Check if this channel is empty, and delete it"
        if len(channel.members) == 0:
            log.warning(f"I should delete {channel.mention}, it's empty...")

    async def validate_category(guild: discord.Guild, category: discord.CategoryChannel):
        "Check if this category has an empty voice channel"
        log.warning(f"validating category {category.mention}")

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

        channels = []
        categories = []
        if before.channel and before.channel.category.id in watch_list:
            log.warning(f"watching! - {before.channel.mention}")
            channels.append(before.channel)
            categories.append(before.channel.category)
        if after.channel and after.channel.category.id in watch_list:
            log.warning(f"watching! - {after.channel.mention}")
            channels.append(after.channel)
            categories.append(after.channel.category)

        for channel in channels:
            self.validate_channel(guild, channel)

        for category in categories:
            self.validate_category(guild, category)

    
    @commands.guild_only()
    @commands.group()
    async def emptyvoices(self, _ctx):
        "Empty Voices"
        pass

    @emptyvoices.command()
    async def watchcat(self, ctx, category: discord.CategoryChannel):
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

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} items in the watchlist.")
