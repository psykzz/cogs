import datetime
from redbot.core import Config, commands
from redbot.core.utils.predicates import MessagePredicate

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
    @commands.guild_only()
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
        relative_time: commands.RelativedeltaConverter
    ):
        "Add a war timer for a zone"

        proper_zone = self.get_proper_zone(zone)
        if not proper_zone:
            await ctx.send(f"{zone} is not a valid zone")
            return

        timer = await self.get_timer_for_zone(ctx, proper_zone)
        if timer:
            await ctx.send(f"found timer for zone: {timer}")
        await ctx.send(f"zone: {proper_zone}")
        await ctx.send(f"time: {datetime.datetime.now() + relative_time}")

        await self.add_timer_for_zone(ctx, proper_zone, relative_time)
        await ctx.send(f"War timer created\n{proper_zone} in {relative_time}")

    @war.command()
    async def remove(
        self, ctx, zone: str
    ):
        "Removes a war timer for a zone"

        guild_config = self.config.guild(ctx.guild)
        timer = await guild_config.timers()
        if not timer:
            await ctx.send(f"There are no active wars set for {zone} to remove.")
            return

        timer_str = ', '.join([f"{index+1}: {timer[zone]}" for index, timer in enumerate(timers)])
        await ctx.send(f"Timers\n{timer_str}\n\nWhich timer would you like to remove?")

        pred = MessagePredicate.valid_int(ctx)
        await self.bot.wait_for("message", check=pred)
        await ctx.send(f"War timer {pred.result} removed.")

    async def get_timer_for_zone(self, ctx, zone):
        guild_config = self.config.guild(ctx.guild)
        timers = await guild_config.timers()

        return timers.get(zone)
    
    async def add_timer_for_zone(self, ctx, zone, relative_time):
        guild_config = self.config.guild(ctx.guild)
        timers = await guild_config.timers()
        async with guild_config.timers() as timers:
            timers[zone] = relative_time

    def get_proper_zone(self, zone):
        # Check if the zone is valid
        lower_zones = [z.lower() for z in VALID_ZONES]
        if zone.lower() not in lower_zones:
            return None
        return VALID_ZONES[lower_zones.index(zone.lower())]
