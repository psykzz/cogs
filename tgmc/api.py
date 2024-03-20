import asyncio

import discord
import httpx
from redbot.core import commands

MARINE_MAJOR_VICTORY = "Marine Major Victory"
XENOMORPH_MAJOR_VICTORY = "Xenomorph Major Victory"
MARINE_MINOR_VICTORY = "Marine Minor Victory"
XENOMORPH_MINOR_VICTORY = "Xenomorph Minor Victory"
SOM_MAJOR_VICTORY = "Sons of Mars Major Victory"
SOM_MINOR_VICTORY = "Sons of Mars Minor Victory"

async def http_get(url):
    max_attempts = 3
    attempt = 0
    while (
        max_attempts > attempt
    ):  # httpx doesn't support retries, so we'll build our own basic loop for that
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url)

            if r.status_code == 200:
                return r.json()
            else:
                attempt += 1
            await asyncio.sleep(5)
        except (httpx._exceptions.ConnectTimeout, httpx._exceptions.HTTPError):
            attempt += 1
            await asyncio.sleep(5)
            pass


class TGMC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_winrate(self, ctx, delta="14", gamemode=None, custom_conditions=None):
        raw_data = await http_get(
            f"https://statbus.psykzz.com/api/winrate?delta={delta}"
        )
        if not raw_data:
            return await ctx.send(
                "Unable to query data - check https://statbus.psykzz.com is online."
            )

        data = raw_data.get("by_gamemode", {}).get(gamemode, {}) if gamemode else raw_data.get("winrates", {})

        winrates = discord.Embed()
        winrates.type = "rich"

        winrates.set_author(
            name="TGMC Statbus", url=f"https://statbus.psykzz.com",
        )

        result_type = [
            MARINE_MAJOR_VICTORY,
            XENOMORPH_MAJOR_VICTORY,
            MARINE_MINOR_VICTORY,
            XENOMORPH_MINOR_VICTORY
        ]

        # If we have a custom win condition, we want to show that instead of xeno
        if custom_conditions:
            result_type = custom_conditions

        total_wins = 0
        for res in result_type:
            wins = data.get(res, 0)
            total_wins += wins

        marine_wins = data.get(MARINE_MAJOR_VICTORY, 0) + data.get(
            MARINE_MINOR_VICTORY, 0
        )
        if total_wins > 0:
            calc_winrates = round((marine_wins / total_wins) * 100, 2)
            winrates.add_field(
                name="Winrate (Marine wins)", value=f"{calc_winrates}%"
            )
        else:
            winrates.add_field(
                name="Winrate (Marine wins)", value=f"`Not enough data`"
            )
        winrates.add_field(
            name="View Raw",
            value=f"https://statbus.psykzz.com/api/winrate?delta={delta}",
            inline=False,
        )

        await ctx.send(embed=winrates)

    @commands.group()
    async def winrates(self, _ctx):
        "Check winrates from the API"
        pass

    @winrates.command()
    async def all(self, ctx, delta="14"):
        "Get the current winrates"
        return await self.get_winrate(ctx, delta, None) # None should get all winrates together

    @winrates.command(aliases=["distresssignal", "distress-signal", "ds"])
    async def distress(self, ctx, delta="14"):
        "Get the current winrates on distress"
        return await self.get_winrate(ctx, delta, "Distress Signal")
        
    @winrates.command()
    async def crash(self, ctx, delta="14"):
        "Get the current winrates on crash"
        return await self.get_winrate(ctx, delta, "Crash")

    @winrates.command(aliases=["buy", "bug-hunt", "bh"])
    async def bughunt(self, ctx, delta="14"):
        "Get the current winrates on bug hunt"
        return await self.get_winrate(ctx, delta, "Bug Hunt")

    @winrates.command(aliases=["party", "hunt-party", "hp"])
    async def huntparty(self, ctx, delta="14"):
        "Get the current winrates on hunt party"
        return await self.get_winrate(ctx, delta, "Hunt party")

    @winrates.command(aliases=["nuclear", "war", "nuclear-war", "nw"])
    async def nuclearwar(self, ctx, delta="14"):
        "Get the current winrates on nuclear war"
        return await self.get_winrate(ctx, delta, "Nuclear War")

    @winrates.command(aliases=["camp"])
    async def campaign(self, ctx, delta="14"):
        "Get the current winrates on campaign"
        return await self.get_winrate(ctx, delta, "Campaign")

    @winrates.command(aliases=["combat", "patrol", "combat-patrol", "cp"])
    async def combatpatrol(self, ctx, delta="14"):
        "Get the current winrates on combat patrol"
        return await self.get_winrate(ctx, delta, "Combat Patrol", [
            MARINE_MAJOR_VICTORY,
            SOM_MAJOR_VICTORY,
            MARINE_MINOR_VICTORY,
            SOM_MINOR_VICTORY
        ])

    @winrates.command(aliases=["sensor", "capture", "sensor-capture", "sc"])
    async def sensorcapture(self, ctx, delta="14"):
        "Get the current winrates on sensor capture"
        return await self.get_winrate(ctx, delta, "Sensor Capture", [
            MARINE_MAJOR_VICTORY,
            SOM_MAJOR_VICTORY,
            MARINE_MINOR_VICTORY,
            SOM_MINOR_VICTORY
        ])
