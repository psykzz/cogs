import asyncio
import logging

import discord
import httpx
from redbot.core import commands

log = logging.getLogger("red.cogs.albion_auth")


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    log.info(f"Making HTTP GET request to {url} with params: {params}")
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=10.0)

            if r.status_code == 200:
                response_data = r.json()
                log.info(f"HTTP GET successful for {url} - Status: {r.status_code}")
                log.debug(f"Response data: {response_data}")
                return response_data
            else:
                attempt += 1
                log.warning(f"HTTP GET failed for {url} - Status: {r.status_code}, Attempt {attempt}/{max_attempts}")
                await asyncio.sleep(2)
        except (httpx.ConnectTimeout, httpx.RequestError) as e:
            attempt += 1
            log.warning(f"HTTP GET error for {url}: {type(e).__name__}: {str(e)}, Attempt {attempt}/{max_attempts}")
            await asyncio.sleep(2)

    log.error(f"HTTP GET failed after {max_attempts} attempts for {url}")
    return None


class AlbionAuth(commands.Cog):
    """Authenticate with Albion Online player names"""

    def __init__(self, bot):
        self.bot = bot

    async def search_player(self, name):
        """Search for a player by name"""
        log.info(f"Searching for player: {name}")
        url = "https://gameinfo-ams.albiononline.com/api/gameinfo/search"
        params = {"q": name}
        result = await http_get(url, params)

        if result and result.get("players"):
            player = result["players"][0]
            log.info(f"Player found: {player.get('Name')} (ID: {player.get('Id')})")
            return player

        log.warning(f"Player '{name}' not found in search results")
        return None

    @commands.guild_only()
    @commands.hybrid_command(name="auth")
    async def auth(self, ctx, name: str):
        """Authenticate with your Albion Online character name

        The bot will search for the player name in Albion Online and rename you to match.

        Usage: .auth <player_name>
        Example: .auth MyCharacter
        """
        log.info(f"Auth command invoked by {ctx.author} for player: {name}")

        async with ctx.typing():
            # Search for the player
            player = await self.search_player(name)
            if not player:
                log.warning(f"Auth command failed: Player '{name}' not found")
                await ctx.send(f"❌ Player '{name}' not found in Albion Online.")
                return

            player_name = player.get("Name", name)
            player_id = player.get("Id")

            log.info(f"Found player: {player_name} (ID: {player_id})")

            # Try to rename the user
            try:
                await ctx.author.edit(nick=player_name)
                log.info(f"Successfully renamed {ctx.author} to {player_name}")
                await ctx.send(
                    f"✅ Successfully authenticated! "
                    f"Your nickname has been changed to **{player_name}**."
                )
            except discord.Forbidden:
                log.error(f"Permission denied: Cannot rename {ctx.author}")
                await ctx.send(
                    "❌ I don't have permission to change your nickname. "
                    "Please contact a server administrator."
                )
            except discord.HTTPException as e:
                log.error(f"Failed to rename {ctx.author}: {e}")
                await ctx.send(f"❌ Failed to change your nickname: {e}")
