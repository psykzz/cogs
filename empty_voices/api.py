import discord
from redbot.core import Config, commands


IDENTIFIER = 1672261474290236288

default_guild = {
    "emptyvoices": {
        "watchlist": [],
    },
}

class EmptyVoices(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )

        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.group()
    async def emptyvoices(self, _ctx):
        "Empty Voices"
        pass

    @emptyvoices.command()
    async def watchcat(self, ctx, category: discord.CategoryChannel):
        "Set a category to watch"

        guild_group = self.config.guild(ctx.guild)
        watch_list = guild_group.emptyvoices.watchlist()

        # Add current channel to watchlist if not there.
        if category.id not in watch_list:
            watch_list.append(category.id)
            await ctx.send(f"{ctx.author.mention}, adding {category.mention} to watchlist.")
        else:
            await ctx.send(f"{ctx.author.mention}, {category.mention} is already on the watchlist.")

        await ctx.send(f"{ctx.author.mention}, there are {len(watch_list)} items in the watchlist.")
