import datetime

from dateutil.relativedelta import relativedelta

from redbot.core import Config, commands
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions

IDENTIFIER = 4175987634259872345  # Random to this cog

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
    async def war(self, ctx):
        "Manage war timers"
        pass

    @war.command()
    async def next(self, ctx, specific_zone: str = None):
        "Get the next upcoming war"
        timer, zone = None, None
        if specific_zone is not None:

            # Get the proper zone name
            proper_zone = self.get_proper_zone(specific_zone)
            if not proper_zone:
                await ctx.send(f"{zone} is not a valid zone")
                return

            # Get the zone timer
            timer = await self.get_timer_for_zone(ctx, proper_zone)
            if not timer:
                await ctx.send(f"There are no upcoming wars for {proper_zone}.")
                return

            relative_time = relativedelta(timer, datetime.datetime.now())
            await ctx.send(
                f"The next war for {proper_zone}, is in {humanize_delta(relative_time, 'minutes')}."
            )
            return

        # We didn't have a specific zone so we should just find the earlist one

        upcoming_war = (zone, timer)  # (none, none)

        # iterate through VALID_ZONE and get the next upcoming war
        for zone in VALID_ZONES:
            timer = await self.get_timer_for_zone(ctx, zone)
            if not timer:
                continue
            if upcoming_war[1] is None:
                upcoming_war = (zone, timer)
                continue
            if timer < upcoming_war[1]:
                upcoming_war = (zone, timer)

        zone, timer = upcoming_war
        if not zone:
            await ctx.send(f"There are no upcoming wars.")
            return
        relative_time = relativedelta(timer, datetime.datetime.now())
        await ctx.send(
            f"The next war is for {zone}, in {humanize_delta(relative_time, 'minutes')}."
        )

    @war.command()
    @commands.mod_or_permissions(manage_channels=True)
    async def add(self, ctx, zone: str, *, relative_time: str):
        "Add a war timer for a zone"

        relative_delta = commands.parse_relativedelta(relative_time)
        if not relative_delta:
            await ctx.send(f"Unable to parse timestamp, try 24h3m or something else.")
            return

        war_time = datetime.datetime.now() + relative_delta

        proper_zone = self.get_proper_zone(zone)
        if not proper_zone:
            await ctx.send(f"{zone} is not a valid zone.")
            return

        timer = await self.get_timer_for_zone(ctx, proper_zone)
        if timer:
            await ctx.send(f"Replacing existing timer for zone: {timer}.")

        await self.add_timer_for_zone(ctx, proper_zone, war_time)
        await ctx.send(
            f"War timer created for {proper_zone}, in {humanize_delta(relative_delta, 'minutes')}."
        )

        # defenders = await self.ask_question(ctx, "Who are the defenders?", {
        #     ":x:": None, ":regional_indicator_c:": "Covenant", 
        #     ":regional_indicator_s:": "Syndicate", ":regional_indicator_m:": "Marauders"
        # })
        # attackers = await self.ask_question(ctx, "Who are the attackers?", {
        #     ":x:": None, ":regional_indicator_c:": "Covenant", 
        #     ":regional_indicator_s:": "Syndicate", ":regional_indicator_m:": "Marauders"
        # })
        # await ctx.send(f"Def: {defenders}, Attk: {attackers}")

        # msg = await ctx.send("Who are the defenders?")
        # emojis = ["❌", "C", "S", "M" ]
        # start_adding_reactions(msg, emojis)
        # pred = ReactionPredicate.with_emojis(emojis, msg)
        # await ctx.bot.wait_for("reaction_add", check=pred)
        # if pred.result == 0:
        #     return
        # # Add this to database

    async def ask_question(self, ctx, question, options):
        msg = await ctx.send(question)
        pred = ReactionPredicate.with_emojis(options.keys(), msg)
        await ctx.bot.wait_for("reaction_add", check=pred)
        await msg.delete()
        return options[options.keys()[pred.result]]  # Oh such a hack

    @war.command()
    @commands.mod_or_permissions(manage_channels=True)
    async def remove(self, ctx, zone: str):
        "Removes a war timer for a zone"

        proper_zone = self.get_proper_zone(zone)
        if not proper_zone:
            await ctx.send(f"{zone} is not a valid zone.")
            return

        timer = await self.get_timer_for_zone(ctx, proper_zone)
        if not timer:
            await ctx.send(f"There are no active wars set for {zone} to remove.")
            return

        await self.add_timer_for_zone(
            ctx, proper_zone, datetime.datetime.now()
        )  # Now will just instantly invalidate the timer
        await ctx.send(f"War timer for {zone} was removed.")

    async def get_timer_for_zone(self, ctx, zone):
        guild_config = self.config.guild(ctx.guild)
        timers = await guild_config.timers()
        timer = timers.get(zone)
        if not timer:
            return None
        datetime_instance = datetime.datetime.fromisoformat(timer)
        if datetime.datetime.now() > datetime_instance:
            return None
        return datetime_instance

    async def add_timer_for_zone(self, ctx, zone, timestamp):
        guild_config = self.config.guild(ctx.guild)
        timers = await guild_config.timers()
        async with guild_config.timers() as timers:
            timers[zone] = timestamp.isoformat()

    def get_proper_zone(self, zone):
        # Check if the zone is valid
        lower_zones = [z.lower() for z in VALID_ZONES]
        if zone.lower() not in lower_zones:
            return None
        return VALID_ZONES[lower_zones.index(zone.lower())]


RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
INFRACTION_FORMAT = "%Y-%m-%d %H:%M"


def _stringify_time_unit(value: int, unit: str) -> str:
    """
    Returns a string to represent a value and time unit, ensuring that it uses the right plural form of the unit.

    >>> _stringify_time_unit(1, "seconds")
    "1 second"
    >>> _stringify_time_unit(24, "hours")
    "24 hours"
    >>> _stringify_time_unit(0, "minutes")
    "less than a minute"
    """
    if value == 1:
        return f"{value} {unit[:-1]}"
    elif value == 0:
        return f"less than a {unit[:-1]}"
    else:
        return f"{value} {unit}"


def humanize_delta(
    delta: relativedelta, precision: str = "seconds", max_units: int = 6
) -> str:
    """
    Returns a human-readable version of the relativedelta.

    precision specifies the smallest unit of time to include (e.g. "seconds", "minutes").
    max_units specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).
    """
    if max_units <= 0:
        raise ValueError("max_units must be positive")

    units = (
        ("years", delta.years),
        ("months", delta.months),
        ("days", delta.days),
        ("hours", delta.hours),
        ("minutes", delta.minutes),
        ("seconds", delta.seconds),
    )

    # Add the time units that are >0, but stop at accuracy or max_units.
    time_strings = []
    unit_count = 0
    for unit, value in units:
        if value:
            time_strings.append(_stringify_time_unit(value, unit))
            unit_count += 1

        if unit == precision or unit_count >= max_units:
            break

    # Add the 'and' between the last two units, if necessary
    if len(time_strings) > 1:
        time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
        del time_strings[-2]

    # If nothing has been found, just make the value 0 precision, e.g. `0 days`.
    if not time_strings:
        humanized = _stringify_time_unit(0, precision)
    else:
        humanized = ", ".join(time_strings)

    return humanized
