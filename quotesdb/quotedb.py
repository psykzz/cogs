import datetime
import logging
import random

import discord
from redbot.core import Config, commands

IDENTIFIER = 1672261474290237490

default_guild = {
    "quotes": {
        "incr": 1,
        "id": {},
        "trigger": {},
    },
}

class QuoteDB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )

        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.command(name=".")
    async def quote_add(self, ctx, trigger: str, *, quote: str):
        'Add a new quote'
        guild_group = self.config.guild(ctx.guild)
        incr = await guild_group.quotes.incr() + 1
        await guild_group.quotes.incr.set(incr)
        async with guild_group.quotes.id() as quotes, guild_group.quotes.trigger() as triggers:
            quotes[incr] = {
                "content": quote,
                "user": ctx.author.id,
                "trigger": trigger,
                "jump_url": ctx.message.jump_url,
                "datetime": datetime.datetime.now().timestamp()
            }

            triggers.setdefault(trigger, [])
            triggers[trigger] += [str(incr)]

        await ctx.send(f"{ctx.author.mention}, added quote `#{incr}`.")

    @commands.guild_only()
    @commands.command(name="..")
    async def quote_show(self, ctx, *, trigger: str):
        'Show a quote'
        
        guild_group = self.config.guild(ctx.guild)

        trigger_data = await guild_group.quotes.trigger()
        triggers = None
        try:
            triggers = trigger_data[trigger]
        except KeyError:
            await ctx.send("Quote not found, add one `.. <trigger> <quote>`")
            return
        quote_id = random.choice(triggers)

        quotes = await guild_group.quotes.id()
        quote = quotes[str(quote_id)]['content']
        await ctx.send(f"`#{quote_id}` :mega: {quote}")

    @commands.guild_only()
    @commands.command(name="qdel")
    async def quote_del(self, ctx, *, qid: str):
        'Delete a quote'
        guild_group = self.config.guild(ctx.guild)
        async with guild_group.quotes.id() as quotes, guild_group.quotes.trigger() as triggers:
            if qid not in quotes:
                await ctx.send(f"{ctx.author.mention}, invalid quote id.")
                return
            data = quotes[qid]
            member = discord.utils.find(lambda m: m.id == data['user'], ctx.channel.guild.members)
            if ctx.author != member:
                await ctx.send(f"{ctx.author.mention}, only the creator (or admins) can delete that.")
                return
            trigger = data['trigger']
            del quotes[qid]
            triggers[trigger].remove(qid)

        await ctx.send(f"{ctx.author.mention}, deleted quote #{qid}.")

    @commands.guild_only()
    @commands.command(name="qid")
    async def quote_info(self, ctx, *, qid: str):
        'Show details about a quote'
        guild_group = self.config.guild(ctx.guild)
        quotes = await guild_group.quotes.id()
        if qid not in quotes:
            await ctx.send(f"{ctx.author.mention}, invalid quote id.")
            return
        data = quotes[qid]
            
        member = discord.utils.find(lambda m: m.id == data['user'], ctx.channel.guild.members)

        log = discord.Embed()
        log.type = "rich"

        log.set_author(name=member, url=data['jump_url'])
        log.title = f"Quote Info - #{qid}"

        created_at = datetime.datetime.fromtimestamp(data['datetime'])
        log.add_field(
            name=f"{data['trigger']}",
            value=f"{data['content']}",
            inline=False
        )
        log.add_field(
            name=f"Author",
            value=f"{member}",
        )
        log.add_field(
            name=f"Created",
            value=f"{created_at}",
        )

        await ctx.send(embed=log)
