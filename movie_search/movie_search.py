import asyncio
import json
import logging
from urllib.parse import quote
from urllib.request import Request, urlopen

from redbot.core import commands

log = logging.getLogger("red.cog.movie_search")


class MovieSearch(commands.Cog):
    """Search IMDb for movies by title."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _search_movies(title):
        encoded_title = quote(title.lower(), safe="")
        first_character = quote(title[0].lower(), safe="")
        request = Request(
            f"https://v3.sg.media-imdb.com/suggestion/{first_character}/{encoded_title}.json",
            headers={"Accept": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            results = json.load(response).get("d", [])
        return [
            {
                "movieID": item["id"][2:],
                "title": item.get("l", title),
                "year": item.get("y"),
            }
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"].startswith("tt")
            and item["id"][2:].isdigit()
        ]

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
            matches = await asyncio.to_thread(self._search_movies, title)
        except Exception:
            log.exception("IMDb search failed for %r", title)
            await ctx.send("IMDb search failed. Please try again later.", ephemeral=True)
            return

        if not matches:
            await ctx.send(f"No IMDb results found for {title!r}.", ephemeral=True)
            return

        movie = matches[0]
        imdb_id = movie.get("movieID")
        if not imdb_id or not str(imdb_id).isdigit():
            await ctx.send("IMDb returned a result without a valid title link.", ephemeral=True)
            return

        movie_title = movie.get("title", title)
        year = movie.get("year")
        display_title = f"{movie_title} ({year})" if year else movie_title
        link = f"https://www.imdb.com/title/tt{imdb_id}/"
        await ctx.channel.send(f"{display_title}: {link}")
