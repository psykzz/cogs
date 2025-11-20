import asyncio
import logging
import re
from typing import Any, Dict, Union

import discord
import httpx
from imdb import Cinemagoer
from redbot.core import Config, checks, commands
from redbot.core.utils.menus import menu

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
            "notify_episode": [],
        }
        self.config.register_guild(**default_guild)
        self._http_client = None

    async def cog_load(self):
        """Initialize HTTP client when cog loads"""
        self._http_client = httpx.AsyncClient()

    async def cog_unload(self):
        """Close HTTP client when cog unloads"""
        if self._http_client:
            await self._http_client.aclose()

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete."""
        return

    async def get_latest_episodes(self, imdb_id: str) -> Union[Dict[str, Any], None]:
        """Get the latest episodes from vidsrc"""
        response = await http_get(
                "https://vidsrc.me/episodes/latest/page-1.json",
                client=self._http_client
            )
        if not response:
            log.info("Response was empty. %s", response)
            return None
        all_data = response.get('result', [])
        log.info("Checking %s episodes against '%s'", len(all_data), imdb_id)
        return next((x for x in all_data if x.get('imdb_id', '') == f"tt{imdb_id}"), None)

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

    @movie.command(name="check")
    async def _movievote_check(self, ctx: commands.Context, *, imdb_link: str):
        """Check vidsrc has a link to the next episode"""
        await ctx.trigger_typing()
        link_group = RE_IMDB_LINK.search(imdb_link)
        link = link_group.group(1) if link_group else None
        if not link:
            await ctx.reply("Add an IMDB link to the command.")
            return
        imdb_id = link.split('/tt')[-1]

        episode = await self.get_latest_episodes(imdb_id)
        if not episode:
            await ctx.send("Unable to get episode data.")
            return

        imdb_data = imdb.get_movie(imdb_id)
        embed = discord.Embed(
            title=f"🎬 {episode.get('show_title', '')}",
            description=f"Episode found! Link: {episode.get('embed_url', '')}",
            url=episode.get('embed_url', '')
        )
        embed.add_field(name="Season", value=episode.get('season', ''), inline=True)
        embed.add_field(name="Episode", value=episode.get('episode', ''), inline=True)
        embed.set_thumbnail(url=imdb_data.get_fullsizeURL())
        await ctx.reply(embed=embed)

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
            if movie["link"] == link:
                movie["watched"] = True
                await ctx.send("Movie marked watched.")
                break
        else:
            await ctx.reply("Couldn't find movie.")
            return

        await self.config.guild(ctx.guild).movies.set(movies)
        await self.update_leaderboard(ctx)

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
            if movie["link"] == link:
                movie["watched"] = False
                await ctx.send("Movie marked unwatched.")
                break
        else:
            await ctx.reply("Couldn't find movie.")
            return

        await self.config.guild(ctx.guild).movies.set(movies)
        await self.update_leaderboard(ctx)

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
        embed = discord.Embed(
            title=f"🎬 {movie['title']} ({movie['year']})",
            description=f"_{', '.join(movie['genres'])}_"
        )
        embed.add_field(name="Score", value=f"{movie['score']}", inline=True)
        embed.add_field(name="Stream", value=f"https://vidsrc.me/embed/tt{movie['imdb_id']}", inline=True)
        embed.set_thumbnail(url=imdb_data.get_fullsizeURL())

        await ctx.reply(embed=embed)

    @movie.command(name="pinboard")
    async def _movievote_pinboard(self, ctx):
        """
            Get the movie pinboard.
            The pinboard will be updated each time a movie is added or removed from the list
            and show the top 5 movies next to be watched.
        """

        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.send("No movies in the list.")
            return

        embed = await self.generate_leaderboard(ctx.guild, 5, True)
        leaderboard = await ctx.send(embed=embed)
        await leaderboard.pin()

        try:
            leaderboard_id = await self.config.guild(ctx.guild).leaderboard()
            if leaderboard_id:
                leaderboard_msg = await ctx.channel.fetch_message(leaderboard_id)
                await leaderboard_msg.unpin()
                await leaderboard_msg.delete()
        except Exception:
            log.error("unable to find delete and unpin previous message")

        # Save the leaderboard message ID so we can edit it later
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard.id)

    @movie.command(name="leaderboard")
    async def _movievote_leaderboard(self, ctx, watched_only=True):
        """
            Get the movie leaderboard.
        """
        movies = await self.config.guild(ctx.guild).movies()
        if not movies:
            await ctx.send("No movies in the list.")
            return

        # filter out movies that have been watched
        if watched_only:
            movies = [movie for movie in movies if not movie.get("watched", False)]

        movies = sorted(movies, key=lambda x: x["score"], reverse=True)

        def generate_page(movie, position):
            title = movie.get("title", "unknown")
            year = movie.get("year", "unknown")
            imdb = movie.get("imdb_id", 00000)
            return f"#{position} {title} ({year}) | https://www.imdb.com/title/tt{imdb}"

        pages = [generate_page(movie, position) for position, movie in enumerate(movies, start=1)]
        await menu(ctx, pages)

    @commands.Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return
        if message.content.startswith(tuple(await self.bot.get_valid_prefixes())):  # Ignore commands
            return
        guild_data = await self.config.guild(message.guild).all()
        try:
            guild_data["channels_enabled"]
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
        imdb_id = link.split('/tt')[-1]

        # Add Imdb link to movie list
        movies = await self.config.guild(message.guild).movies()
        exists = False
        for m in movies:
            if m["imdb_id"] == imdb_id:
                exists = True
                break
        if exists:
            await message.reply(f"{link} is already in the list.")
            await message.delete()
            return

        try:
            imdb_movie = imdb.get_movie(imdb_id)
            movie = {
                "link": link, "imdb_id": imdb_id, "score": 0, "watched": False}
            movie["title"] = imdb_movie.get("title")
            movie["genres"] = imdb_movie.get("genres")
            movie["year"] = imdb_movie.get("year")
            movies.append(movie)
        except Exception:
            await message.reply("Error getting movie from IMDB.")
            return
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
        imdb_id = link.split('/tt')[-1]

        guild_data = await self.config.guild(message.guild).all()
        try:
            guild_data["channels_enabled"]
        except KeyError:
            return
        if message.channel.id not in await self.config.guild(message.guild).channels_enabled():
            return

        movies = await self.config.guild(message.guild).movies()
        for movie in movies:
            if movie["imdb_id"] == imdb_id:
                movies.remove(movie)
                await self.config.guild(message.guild).movies.set(movies)
                break

        await self.update_leaderboard(message)

    async def _is_movie_channel(self, payload) -> bool:
        """Check if a reaction payload is from a movie channel."""
        if not payload.guild_id:
            return False

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return False

        try:
            enabled_channels = await self.config.guild(guild).channels_enabled()
            return payload.channel_id in enabled_channels
        except Exception:
            log.exception("Error checking if channel is enabled for movie voting")
            return False

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Only process reactions in movie channels
        if not await self._is_movie_channel(payload):
            return

        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        # Use get methods first (cached), fallback to fetch only if needed
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            channel = await self.bot.fetch_channel(payload.channel_id)

        # Fetch message to get reactions
        message = await channel.fetch_message(payload.message_id)

        user = self.bot.get_user(payload.user_id)
        if not user:
            user = await self.bot.fetch_user(payload.user_id)

        emoji = payload.emoji

        log.info(f"Reaction added. {user.name} on '{message.clean_content}'")
        await self.count_votes(message, emoji)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # Only process reactions in movie channels
        if not await self._is_movie_channel(payload):
            return

        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        # Use get methods first (cached), fallback to fetch only if needed
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            channel = await self.bot.fetch_channel(payload.channel_id)

        # Fetch message to get reactions
        message = await channel.fetch_message(payload.message_id)

        user = self.bot.get_user(payload.user_id)
        if not user:
            user = await self.bot.fetch_user(payload.user_id)

        emoji = payload.emoji

        log.info(f"Reaction removed. {user.name} on '{message.clean_content}'")
        await self.count_votes(message, emoji)

    async def count_votes(self, message, emoji):
        if not message.guild:
            return

        # Find links in message
        link_group = RE_IMDB_LINK.search(message.content)
        link = link_group.group(1) if link_group else None
        if not link:
            return
        imdb_id = link.split('/tt')[-1]
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
            if movie["imdb_id"] == imdb_id:
                movie["score"] = upvotes - dnvotes
        await self.config.guild(message.guild).movies.set(movies)

        # Update the loadboard message with new scores
        await self.update_leaderboard(message)

    async def update_leaderboard(self, message):
        log.info("Updating leaderboard")
        leaderboard_id = await self.config.guild(message.guild).leaderboard()
        if leaderboard_id:
            leaderboard_msg = await message.channel.fetch_message(leaderboard_id)

            embed = await self.generate_leaderboard(message.guild)  # type: ignore
            await leaderboard_msg.edit(embed=embed)

    async def generate_leaderboard(self, guild: discord.Guild, limit=5, watched_only=True):
        # Save the leaderboard message ID so we can edit it later
        movies = await self.config.guild(guild).movies()
        if not movies:
            return

        # filter out movies that have been watched
        if watched_only:
            movies = [movie for movie in movies if not movie["watched"]]

        embed = discord.Embed(title="Movie Leaderboard 🎬", description="Showing the Top 5 films to be watched")
        movies = sorted(movies, key=lambda x: x["score"], reverse=True)

        # sublist
        movie_list = movies[:limit] if limit else movies

        if limit > 5:
            # We must use the ugly style because of discord limits
            ugly_field_value = ""
            for position, movie in enumerate(movie_list, start=1):
                try:
                    ugly_field_value += (
                        f"#{position} {movie['title']} ({movie['year']})\n"
                        f"_{', '.join(movie['genres'])}_\n"
                        f"[IMDB](https://www.imdb.com/title/tt{movie['imdb_id']})\n\n\n"
                    )
                except Exception as e:
                    log.exception(f"Unable to parse pos: {position} - {movie['title']}", e)
            embed.description = ugly_field_value
            return embed

        for position, movie in enumerate(movie_list, start=1):
            embed.add_field(
                name=f"#{position} {movie['title']} ({movie['year']})",
                value=f"_{', '.join(movie['genres'])}_\n[IMDB](https://www.imdb.com/title/tt{movie['imdb_id']})",
                inline=True
            )
            embed.add_field(name="Score", value=f"{movie['score']}", inline=True)
            embed.add_field(name="\u200B", value="\u200B")  # Empty field
        return embed

    # Updates movies to new format
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
        except Exception:
            return original_movie

    # Loop through old movies and update them to the new format
    async def update_movies(self, ctx):
        movies = await self.config.guild(ctx.guild).movies()
        for movie in movies:
            movie = await self.update_movie(movie)

        await self.config.guild(ctx.guild).movies.set(movies)

    # Helper function to fix emojis
    def fix_custom_emoji(self, emoji):
        if emoji[:2] != "<:":
            return emoji
        for guild in self.bot.guilds:
            for e in guild.emojis:
                if str(e.id) == emoji.split(":")[2][:-1]:
                    return e
        return None


async def http_get(url, client=None):
    """Make HTTP GET request with retries

    Args:
        url: URL to fetch
        client: Optional httpx.AsyncClient to reuse. If None, creates a new one.
    """
    max_attempts = 3
    attempt = 0

    # Create client if not provided
    should_close = client is None
    if should_close:
        client = httpx.AsyncClient()

    try:
        while max_attempts > attempt:
            try:
                r = await client.get(url, headers={"user-agent": "psykzz-cogs/1.0.0"})
                if r.status_code == 200:
                    return r.json()
                else:
                    attempt += 1
                await asyncio.sleep(1)
            except (httpx._exceptions.ConnectTimeout, httpx._exceptions.HTTPError):
                attempt += 1
                await asyncio.sleep(1)
        return None
    finally:
        # Only close if we created it
        if should_close:
            await client.aclose()
