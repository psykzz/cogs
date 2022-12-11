import asyncio
import logging
import re

import discord
from imdb import Cinemagoer
from redbot.core import Config, checks, commands

imdb = Cinemagoer()
RE_IMDB_LINK = re.compile(r"(https:\/\/www\.imdb\.com\/title\/tt\d+)")

log = logging.getLogger("red.cog.movie_vote")

class MovieVote(commands.Cog):
    """Manage a channel for collecting votes for what to watch next."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1494641511)

        default_guild = {
            "channels_enabled": [],
            "movies": [],
            "leaderboard": 0,
            "up_emoji": "👍",
            "dn_emoji": "👎",
        }
        self.config.register_guild(**default_guild)

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete."""
        return

    @commands.group(autohelp=False)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def movie(self, ctx):
        """Movie cog settings"""

        if ctx.invoked_subcommand is not None:
            return
        
        await ctx.send_help()

        guild_data = await self.config.guild(ctx.guild).all()
        bad_channels = []
        msg = "Active Channels:\n"
        if not guild_data["channels_enabled"]:
            msg += "None."
        else:
            channel_list = []
            for chan_id in guild_data["channels_enabled"]:
                channel_obj = self.bot.get_channel(chan_id)
                if hasattr(channel_obj, 'name'):
                    channel_list.append(channel_obj)
                else:
                    bad_channels.append(chan_id)
            if not channel_list:
                msg = "None."
            else:
                msg += "\n".join(chan.name for chan in channel_list)

        msg += f"\nUp/down emojis: {guild_data['up_emoji']} / {guild_data['dn_emoji']}"

        embed = discord.Embed(colour=await ctx.embed_colour(), description=msg)
        await ctx.send(embed=embed)

        if bad_channels:
            new_channel_list = [x for x in guild_data["channels_enabled"] if x not in bad_channels]
            await self.config.guild(ctx.guild).channels_enabled.set(new_channel_list)

    @movie.command(name="updatedb")
    async def _movievote_updatedb(self, ctx):
        'Loop through all the movies, update their imdb data'
        await self.update_movies(ctx)
        await ctx.reply("Updating, this might take some time.")
        
    


    @movie.command(name="on")
    async def _movievote_on(self, ctx):
        """Turn on MovieVote in the current channel"""

        channel_id = ctx.message.channel.id
        channels = await self.config.guild(ctx.guild).channels_enabled()
        if not channels:
            await self.config.guild(ctx.guild).channels_enabled.set([])

        if channel_id in channels:
            await ctx.send("MovieVote is already on in this channel.")
        else:
            channels.append(channel_id)
            await self.config.guild(ctx.guild).channels_enabled.set(channels)
            await ctx.send("MovieVote is now on in this channel.")

    @movie.command(name="off")
    async def _movievote_off(self, ctx):
        """Turn off MovieVote in the current channel"""

        channel_id = ctx.message.channel.id
        channels = await self.config.guild(ctx.guild).channels_enabled()
        if not channels:
            await self.config.guild(ctx.guild).channels_enabled.set([])
        if channel_id not in channels:
            await ctx.send("MovieVote is already off in this channel.")
        else:
            channels.remove(channel_id)
            await self.config.guild(ctx.guild).channels_enabled.set(channels)
            await ctx.send("MovieVote is now off in this channel.")

    @movie.command(name="upemoji")
    async def _movievote_upemoji(self, ctx, emoji):
        """Set the upvote emoji"""

        emoji = self.fix_custom_emoji(emoji)
        if emoji is None:
            await ctx.send("That's not a valid emoji.")
            return
        await self.config.guild(ctx.guild).up_emoji.set(str(emoji))
        await ctx.send("Upvote emoji set to: " + str(emoji))

    @movie.command(name="downemoji")
    async def _movievote_downemoji(self, ctx, emoji):
        """Set the downvote emoji"""

        emoji = self.fix_custom_emoji(emoji)
        if emoji is None:
            await ctx.send("That's not a valid emoji.")
            return
        await self.config.guild(ctx.guild).dn_emoji.set(str(emoji))
        await ctx.send("Downvote emoji set to: " + str(emoji))

    @movie.command(name="watch")
    async def _movievote_watch(self, ctx, *, imdb_link):
        """Mark a movie as watched"""

        link_group = RE_IMDB_LINK.search(imdb_link)
        link = link_group.group(1) if link_group else None
        if not link:
            await ctx.reply("Add an IMDB link to the command.")
            return

        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.reply("No movies in the list.")
            return
        for movie in movies:
            if movie["imdb_id"] == link:
                movie["watched"] = True
                await ctx.send("Movie marked watched.")
                break
        else:
            await ctx.reply("Couldn't find movie.")
            return

        await self.config.guild(ctx.guild).movies.set(movies)

    @movie.command(name="rewatch")
    async def _movievote_rewatch(self, ctx, *, imdb_link):
        """Mark a movie as unwatched"""

        link_group = RE_IMDB_LINK.search(imdb_link)
        link = link_group.group(1) if link_group else None
        if not link:
            await ctx.reply("Add an IMDB link to the command.")
            return

        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.reply("No movies in the list.")
            return
        for movie in movies:
            if movie["imdb_id"] == link:
                movie["watched"] = False
                await ctx.send("Movie marked unwatched.")
                break
        else:
            await ctx.reply("Couldn't find movie.")
            return

        await self.config.guild(ctx.guild).movies.set(movies)

    @movie.command(name="next")
    async def _movievote_next(self, ctx):
        """Get the next movie to watch.
        Looks at all movies (minus those marked watched) returns the one with the highest score."""
            
        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.send("No movies in the list.")
            return

        movies = [x for x in movies if not x["watched"]]
        if not movies:
            await ctx.send("All movies have been marked watched.")
            return

        movies = sorted(movies, key=lambda x: x["score"], reverse=True)
        movie = movies[0]

        imdb_data = imdb.get_movie(movie['imdb_id'])
        embed =  discord.Embed(title=f"🎬 {movie['title']} ({movie['year']})", description=f"_{', '.join(movie['genres'])}_")
        embed.add_field(name=f"Score", value=f"{movie['score']}", inline=True)
        embed.set_thumbnail(url=imdb_data.get_fullsizeURL())

        await ctx.reply(embed=embed)

    @movie.command(name="leaderboard")
    async def _movievote_leaderboard(self, ctx):
        """
            Get the movie leaderboard.
            The leaderboard will be updated each time a movie is added or removed from the list.
        """
        
        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.send("No movies in the list.")
            return

        movies = sorted(movies, key=lambda x: x["score"], reverse=True)
        msg = "Movie Leaderboard:\n"
        for movie in movies:
            msg += "**{}** (score: {})\n".format(movie["title"], movie["score"])
        embed = discord.Embed(description=msg)
        leaderboard = await ctx.send(embed=embed)

        # Save the leaderboard message ID so we can edit it later
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard.id)

    def fix_custom_emoji(self, emoji):
        if emoji[:2] != "<:":
            return emoji
        for guild in self.bot.guilds:
            for e in guild.emojis:
                if str(e.id) == emoji.split(":")[2][:-1]:
                    return e
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return
        if message.content.startswith(tuple(await self.bot.get_valid_prefixes())):  # Ignore commands
            return
        guild_data = await self.config.guild(message.guild).all()
        try:
            test = guild_data["channels_enabled"]
        except KeyError:
            return
        if message.channel.id not in await self.config.guild(message.guild).channels_enabled():
            return
        if message.author.id == self.bot.user.id:
            return

        # Find links in message
        link_group = RE_IMDB_LINK.search(message.content)
        link = link_group.group(1) if link_group else None
        if not link:
            return

        # Add Imdb link to movie list
        movies = await self.config.guild(message.guild).movies()
        movie = {"imdb_id": link, "score": 0, "watched": False}
        exists = False
        for m in movies:
            if m["imdb_id"] == link:
                exists = True
                break
        if exists:
            await message.reply(f"{link} is already in the list.")
            await message.delete()
            return

        movies.append(movie)
        await self.config.guild(message.guild).movies.set(movies)
    
        # Still need to fix error (discord.errors.NotFound) on first run of cog
        # must be due to the way the emoji is stored in settings/json
        try:
            up_emoji = await self.config.guild(message.guild).up_emoji()
            dn_emoji = await self.config.guild(message.guild).dn_emoji()
            await message.add_reaction(up_emoji)
            await asyncio.sleep(0.5)
            await message.add_reaction(dn_emoji)
        except discord.errors.HTTPException:
            # Implement a non-spammy way to alert users in future
            pass

        await self.update_leaderboard(message)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        # Remove movie from list if it was deleted
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return

        # Find links in message
        link_group = RE_IMDB_LINK.search(message.content)
        link = link_group.group(1) if link_group else None
        if not link:
            return

        guild_data = await self.config.guild(message.guild).all()
        try:
            test = guild_data["channels_enabled"]
        except KeyError:
            return
        if message.channel.id not in await self.config.guild(message.guild).channels_enabled():
            return

        movies = await self.config.guild(message.guild).movies()
        for movie in movies:
            if movie["imdb_id"] == link:
                movies.remove(movie)
                await self.config.guild(message.guild).movies.set(movies)
                break

        await self.update_leaderboard(message)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = await self.bot.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = await self.bot.fetch_user(payload.user_id)
        emoji = payload.emoji

        if user.id == self.bot.user.id:
            return

        log.info("Reaction added")
        await self.count_votes(message, emoji)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        channel = await self.bot.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = await self.bot.fetch_user(payload.user_id)
        emoji = payload.emoji

        if user.id == self.bot.user.id:
            return
            
        log.info("Reaction removed")
        await self.count_votes(message, emoji)


    async def count_votes(self, message, emoji):
        if not message.guild:
            return

        # Find links in message
        link_group = RE_IMDB_LINK.search(message.content)
        link = link_group.group(1) if link_group else None
        if not link:
            return
        log.info(f"Handling {link}")

        if message.channel.id not in await self.config.guild(message.guild).channels_enabled():
            log.info(f"Wrong channel {message.channel.id}")
            return

        up_emoji = await self.config.guild(message.guild).up_emoji()
        dn_emoji = await self.config.guild(message.guild).dn_emoji()
        if str(emoji) not in (up_emoji, dn_emoji):
            log.info(f"Wrong emoji {emoji}, vs {(up_emoji, dn_emoji)}")
            return

        # We have a valid vote so we can count the votes now
        upvotes, dnvotes = 0, 0
        for react in message.reactions:
            if react.emoji == up_emoji:
                upvotes = react.count
            elif react.emoji == dn_emoji:
                dnvotes = react.count

        # Update the movie with the new score
        movies = await self.config.guild(message.guild).movies()
        log.info(f"Updating {link} with new score: {upvotes - dnvotes}")
        for movie in movies:
            if movie["title"] == link:
                movie["score"] = upvotes - dnvotes 
        await self.config.guild(message.guild).movies.set(movies)

        # Update the loadboard message with new scores
        await self.update_leaderboard(message)
        

    async def update_leaderboard(self, message):
        log.info("Updating leaderboard")
        leaderboard_id = await self.config.guild(message.guild).leaderboard()
        if leaderboard_id:
            leaderboard_msg = await message.channel.fetch_message(leaderboard_id)
            
            embed = await self.generate_leaderboard(message.guild) # type: ignore
            await leaderboard_msg.edit(embed=embed)


    async def generate_leaderboard(self, guild: discord.Guild):
        # Save the leaderboard message ID so we can edit it later
        movies = await self.config.guild(guild).movies()
        if not movies:
            return

        embed =  discord.Embed(title="Movie Leaderboard 🎬", description="Showing the Top 5 films to be watched")
        movies = sorted(movies, key=lambda x: x["score"], reverse=True)
        for position, movie in enumerate(movies[:5], start=1):
            embed.add_field(name=f"#{position} {movie['title']} ({movie['year']})", value=f"_{', '.join(movie['genres'])}_\nhttps://www.imdb.com/title/tt{movie['imdb_id']}", inline=True)
            embed.add_field(name=f"Score", value=f"{movie['score']}", inline=True)
            embed.add_field(name=f"\u200B", value=f"\u200B") # Empty field
        return embed


    async def update_movie(self, original_movie):
        movie = original_movie
        try:
            # Update old style movies
            if movie['title'].startswith('http'):
                movie["link"] = movie["title"]
                movie['imdb_id'] = movie['link'].split('/tt')[-1]

            # Get movie info from IMDB
            imdb_movie = imdb.get_movie(movie['imdb_id'])
            movie["title"] = imdb_movie.get("title") 
            movie["genres"] = imdb_movie.get("genres") 
            movie["year"] = imdb_movie.get("year") 
            log.info("Updated movie: %s", movie["title"])
            return movie
        except:
            return original_movie



    async def update_movies(self, ctx):
        movies = await self.config.guild(ctx.guild).movies()
        for movie in movies:
            movie = await self.update_movie(movie)
            
        await self.config.guild(ctx.guild).movies.set(movies)

