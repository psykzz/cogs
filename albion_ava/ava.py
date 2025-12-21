import asyncio
import logging
from typing import Dict, List, Optional

import httpx
from redbot.core import commands, Config, checks

log = logging.getLogger("red.cogs.albion_ava")


async def http_get(url, headers=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    log.debug(f"Making HTTP GET request to {url}")
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=headers, timeout=10.0)

            if r.status_code == 200:
                response_data = r.json()
                log.debug(f"HTTP GET successful for {url} - Status: {r.status_code}")
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


class AlbionAva(commands.Cog):
    """Track Roads of Avalon connections via Portaler API"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=73602, force_registration=True)
        self.config.register_guild(
            portaler_token=None,
            portaler_guild_id=None,  # Extracted from first successful API call
            home_zone=None,
            last_map_data=None,  # Cache of last successful map data
        )
        self._check_task = None

    async def cog_load(self):
        """Start the background task when cog loads"""
        self._check_task = self.bot.loop.create_task(self._update_loop())
        log.debug("Started Portaler API check task")

    async def cog_unload(self):
        """Cancel the background task when cog unloads"""
        if self._check_task:
            self._check_task.cancel()
            log.debug("Cancelled Portaler API check task")

    async def _update_loop(self):
        """Background task to check Portaler API periodically"""
        await self.bot.wait_until_ready()
        log.debug("Portaler update loop started")

        while True:
            try:
                # Check every 5 minutes
                await asyncio.sleep(300)
                await self._fetch_all_guilds_data()
            except asyncio.CancelledError:
                log.debug("Portaler update loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in Portaler update loop: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying on error

    async def _fetch_all_guilds_data(self):
        """Fetch data for all guilds with configured tokens"""
        for guild in self.bot.guilds:
            try:
                token = await self.config.guild(guild).portaler_token()
                guild_id = await self.config.guild(guild).portaler_guild_id()

                if not token:
                    continue

                # If we don't have a guild_id yet, try to get it from the API
                if not guild_id:
                    # The guild_id would typically be in the API URL
                    # For now, we'll skip guilds without a guild_id
                    log.debug(f"No Portaler guild ID configured for {guild.name}")
                    continue

                map_data = await self._fetch_portaler_data(guild_id, token)
                if map_data:
                    await self.config.guild(guild).last_map_data.set(map_data)
                    log.debug(f"Updated map data for guild {guild.name}")

            except Exception as e:
                log.error(f"Error fetching data for guild {guild.name}: {e}", exc_info=True)

    async def _fetch_portaler_data(self, guild_id: str, token: str) -> Optional[Dict]:
        """Fetch map data from Portaler API"""
        url = f"https://portaler.app/api/map/list/{guild_id}?mergeWithPublic=true"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}"
        }

        log.debug(f"Fetching Portaler data for guild ID: {guild_id}")
        return await http_get(url, headers=headers)

    def _build_connection_graph(self, map_data: Dict, home_zone: str) -> List[str]:
        """Build a text representation of connections from home zone

        Args:
            map_data: Map data from Portaler API
            home_zone: The zone to show connections from

        Returns:
            List of strings representing the connection graph
        """
        if not map_data:
            return ["No map data available"]

        # The Portaler API returns a structure with zones and connections
        # We need to parse it and build a graph showing connections from home_zone
        lines = [f"**Connections from {home_zone}:**", ""]

        zones = map_data.get("zones", [])
        if not zones:
            return ["No zones found in map data"]

        # Find the home zone in the data
        home_zone_data = None
        for zone in zones:
            zone_name = zone.get("name", "")
            if zone_name.lower() == home_zone.lower():
                home_zone_data = zone
                break

        if not home_zone_data:
            return [f"Home zone '{home_zone}' not found in current map data"]

        # Get connections from the home zone
        connections = home_zone_data.get("connections", [])
        if not connections:
            return [f"No connections found from {home_zone}"]

        # Build the connection list
        for i, connection in enumerate(connections, 1):
            target_zone = connection.get("targetZone", "Unknown")
            portal_size = connection.get("size", "Unknown")
            time_left = connection.get("timeLeft", "Unknown")
            lines.append(f"{i}. **{target_zone}** (Size: {portal_size}, Time: {time_left})")

        return lines

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.group(name="setava")
    async def setava(self, ctx):
        """Configure Avalon road tracker settings"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @setava.command(name="token")
    async def setava_token(self, ctx, guild_id: str, *, token: str):
        """Set the Portaler API bearer token and guild ID

        The guild_id is the numeric ID in the Portaler API URL.
        The token is your Portaler API bearer token.

        Usage: [p]setava token <guild_id> <token>
        Example: [p]setava token 1265396129902629046 your_bearer_token_here
        """
        # Store both token and guild_id
        await self.config.guild(ctx.guild).portaler_token.set(token)
        await self.config.guild(ctx.guild).portaler_guild_id.set(guild_id)
        log.debug(f"Set Portaler token and guild ID for {ctx.guild.name}")

        # Try to fetch data immediately to validate the token
        map_data = await self._fetch_portaler_data(guild_id, token)
        if map_data:
            await self.config.guild(ctx.guild).last_map_data.set(map_data)
            await ctx.send("✅ Portaler token and guild ID set successfully! Data fetched and cached.")
        else:
            await ctx.send(
                "⚠️ Portaler token and guild ID set, but failed to fetch data. "
                "Please verify your token and guild ID are correct."
            )

    @setava.command(name="home")
    async def setava_home(self, ctx, *, zone: str):
        """Set the home zone to focus connections from

        The zone name should match the zone name in Albion Online.

        Usage: [p]setava home <zone>
        Example: [p]setava home Lymhurst
        """
        await self.config.guild(ctx.guild).home_zone.set(zone)
        log.debug(f"Set home zone to '{zone}' for {ctx.guild.name}")
        await ctx.send(f"✅ Home zone set to **{zone}**")

    @commands.guild_only()
    @commands.command(name="ava")
    async def ava(self, ctx):
        """Display connections from the home zone

        Shows a graph of current Roads of Avalon connections from your configured home zone.
        """
        async with ctx.typing():
            # Get configuration
            home_zone = await self.config.guild(ctx.guild).home_zone()
            map_data = await self.config.guild(ctx.guild).last_map_data()

            if not home_zone:
                await ctx.send(
                    "❌ No home zone configured. Use `[p]setava home <zone>` to set one."
                )
                return

            if not map_data:
                await ctx.send(
                    "❌ No map data available. Please configure your Portaler token first with "
                    "`[p]setava token <guild_id> <token>`, or wait for the next data refresh."
                )
                return

            # Build connection graph
            graph_lines = self._build_connection_graph(map_data, home_zone)
            graph_text = "\n".join(graph_lines)

            # Send the graph
            if len(graph_text) <= 2000:
                await ctx.send(graph_text)
            else:
                # Split into multiple messages if needed
                chunks = []
                current_chunk = []
                current_length = 0

                for line in graph_lines:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 1900:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_length = line_length
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for chunk in chunks:
                    await ctx.send(chunk)
                    await asyncio.sleep(0.5)
