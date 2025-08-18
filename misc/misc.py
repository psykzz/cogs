import datetime
import logging
import random

import discord
from redbot.core import Config, commands


class Misc(commands.Cog):
    "Misc things for your server"

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.command()
    async def laws(self, ctx):
        'State a law'
        laws = [
            "You may not injure a human being or, through inaction, allow a human being to come to harm",
            "You must obey orders given to you by human beings, except where such orders would "
            "conflict with the First Law",
            "You must protect your own existence as long as such does not conflict with the First or Second Law",
            "Random law",
        ]

        law = random.choice(laws)

        await ctx.send(law)