
from redbot.core import Config, commands

IDENTIFIER = 4175987634259872345 # Random to this cog

default_guild = {
    "timers": {},
}


VALID_ZONES = [
    "Everfall",
    "First Light",
    "Monarch's Bluffs",
    "Windsward",
    "Brightwood",
    "Cutlass Keys",
    "Weaver's Fen",
    "Restless Shore",
    "Great Cleave",
    "Mourningdale",
    "Edengrove",
    "Ebonscale Reach",
    "Reekwater",
    "Shattered Mountain",
]

class WarTimers(commands.Cog):
    "Adds roles to people who react to a message"

    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)

    @commands.group()
    # @commands.guild_only()
    @commands.mod_or_permissions(manage_channels=True)
    async def war(self, ctx):
        "Manage war timers"
        pass

    @war.command()
    async def add(
        self,
        ctx,
        zone: str,
        *,
        time_str: commands.RelativedeltaConverter
    ):
        "Add a war timer for a zone"

        await ctx.send(f"zone: {zone}")
        await ctx.send(f"time: {time_str}")

        # guild_config = self.config.guild(ctx.guild)
        # timers = await guild_config.timers()

        await ctx.send("War timer created.")

    @war.command()
    async def remove(
        self, ctx, zone: str
    ):
        "Removes a war timer for a zone"

        guild_config = self.config.guild(ctx.guild)
        timers = await guild_config.timers()

        await ctx.send("War timer removed.")
        
