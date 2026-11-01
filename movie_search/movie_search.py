import asyncio
import logging

from imdb import Cinemagoer
from redbot.core import commands

log = logging.getLogger("red.cog.movie_search")


class MovieSearch(commands.Cog):
    """Search IMDb for movies by title."""

    def __init__(self, bot):
        self.bot = bot
        self.imdb_client = Cinemagoer()

    @commands.hybrid_command(name="imdb")
    async def imdb(self, ctx, *, title: str):
        """Search IMDb for a movie title and return its link.

        Parameters
        ----------
        title : str
            Movie title to search for
        """
        title = title.strip()
        if not title:
            await ctx.send("Please provide a movie title.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        try:
            matches = await asyncio.to_thread(self.imdb_client.search_movie, title)
        except Exception:
            log.exception("IMDb search failed for %r", title)
            await ctx.send("IMDb search failed. Please try again later.", ephemeral=True)
            return

        if not matches:
            await ctx.send(f"No IMDb results found for {title!r}.", ephemeral=True)
            return

        movie = matches[0]
        imdb_id = getattr(movie, "movieID", None)
        if not imdb_id or not str(imdb_id).isdigit():
            await ctx.send("IMDb returned a result without a valid title link.", ephemeral=True)
            return

        movie_title = movie.get("title", title)
        year = movie.get("year")
        display_title = f"{movie_title} ({year})" if year else movie_title
        link = f"https://www.imdb.com/title/tt{imdb_id}/"
        await ctx.channel.send(f"{display_title}: {link}")
