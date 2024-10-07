import discord
from redbot.core import Config, commands


IDENTIFIER = 1672261474290236288

default_guild = {
    "emptyvoices": {
        "watchlist": [],
        "temp_channels": [],
    },
}

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
            await guild.owner.send("I should delete {channel.mention}, it's empty...")

    async def validate_category(guild: discord.Guild, category: discord.CategoryChannel):
        "Check if this category has an empty voice channel"
        pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return

        watch_list = await guild_group.emptyvoices.watchlist()

        guild = member.guild
        if not guild:
            return

        channels = []
        categories = []
        if before.channel and before.channel.category in watch_list:
            await guild.owner.send("watching!")
            channels.append(before.channel)
            categories.append(before.channel.category)
        if after.channel and after.channel.category in watch_list:
            await guild.owner.send("watching!")
            channels.append(after.channel)
            categories.append(after.channel.category)

        for channel in channels:
            validate_channel(guild, channel)

        for category in categories:
            validate_category(guild, category)

    
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
