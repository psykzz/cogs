import datetime
import logging
import random

import asyncio
import httpx

import discord
from redbot.core import Config, commands

MARINE_MAJOR_VICTORY = "Marine Major Victory"
XENOMORPH_MAJOR_VICTORY = "Xenomorph Major Victory"
MARINE_MINOR_VICTORY = "Marine Minor Victory"
XENOMORPH_MINOR_VICTORY = "Xenomorph Minor Victory"

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

    async def get_winrate(self, ctx, delta="14", gamemode=None):
        raw_data = await http_get(
            f"http://statbus.psykzz.com:8080/api/winrate?delta={delta}"
        )
        if not raw_data:
            return await ctx.send(
                "Unable to query data - check http://statbus.psykzz.com:8080 is online."
            )

        data = raw_data.get("by_gamemode", {}).get(gamemode, {}) if gamemode else raw_data.get("winrates", {})

        winrates = discord.Embed()
        winrates.type = "rich"

        winrates.set_author(
            name="TGMC Statbus", url=f"http://statbus.psykzz.com:8080",
        )

        result_type = [
            MARINE_MAJOR_VICTORY,
            XENOMORPH_MAJOR_VICTORY,
            MARINE_MINOR_VICTORY,
            XENOMORPH_MINOR_VICTORY
        ]
        total_wins = 0
        for res in result_type:
            wins = data.get(res, 0)
            total_wins += wins

        xeno_wins = data.get(XENOMORPH_MAJOR_VICTORY, 0) + data.get(
            XENOMORPH_MINOR_VICTORY, 0
        )
        if total_wins > 0:
            calc_winrates = round((xeno_wins / total_wins) * 100, 2)
            winrates.add_field(
                name="Winrate (Xenomorph to Marine)", value=f"{calc_winrates}%"
            )
        else:
            winrates.add_field(
                name="Winrate (Xenomorph to Marine)", value=f"`Not enough data`"
            )
        winrates.add_field(
            name="View Raw",
            value=f"http://statbus.psykzz.com:8080/api/winrate?delta={delta}",
            inline=False,
        )

        await ctx.send(embed=winrates)

    @commands.group()
    async def winrates(self, ctx):
        "Check winrates from the API"
        pass

    @winrates.command()
    async def all(self, ctx, delta="14"):
        "Get the current winrates"
        return await self.get_winrate(ctx, delta, None) # None should get all winrates together

    @winrates.command()
    async def distress(self, ctx, delta="14"):
        "Get the current winrates on distress"
        return await self.get_winrate(ctx, delta, "Distress Signal")
        

    @winrates.command()
    async def crash(self, ctx, delta="14"):
        "Get the current winrates on crash"
        return await self.get_winrate(ctx, delta, "Crash")

    @winrates.command()
    async def bughunt(self, ctx, delta="14"):
        "Get the current winrates on bug hunt"
        return await self.get_winrate(ctx, delta, "Bug Hunt")

    @winrates.command()
    async def huntparty(self, ctx, delta="14"):
        "Get the current winrates on hunt party"
        return await self.get_winrate(ctx, delta, "Hunt party")

    @winrates.command()
    async def nuclearwar(self, ctx, delta="14"):
        "Get the current winrates on nuclear war"
        return await self.get_winrate(ctx, delta, "Nuclear War")
