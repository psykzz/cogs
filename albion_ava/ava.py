import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

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
        try:
            self._check_task = self.bot.loop.create_task(self._update_loop())
            log.debug("Started Portaler API check task")
        except Exception as e:
            log.error(f"Failed to start Portaler API check task: {e}", exc_info=True)

    async def cog_unload(self):
        """Cancel the background task when cog unloads"""
        if self._check_task:
            self._check_task.cancel()
            log.debug("Cancelled Portaler API check task")

    async def _update_loop(self):
        """Background task to check Portaler API periodically"""
        await self.bot.wait_until_ready()
        log.debug("Portaler update loop started")

        # Do an initial fetch immediately
        try:
            await self._fetch_all_guilds_data()
        except Exception as e:
            log.error(f"Error in initial Portaler data fetch: {e}", exc_info=True)

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
                    # API returns an array, so we store it as-is
                    await self.config.guild(guild).last_map_data.set(map_data)
                    log.debug(f"Updated map data for guild {guild.name}")

            except Exception as e:
                log.error(f"Error fetching data for guild {guild.name}: {e}", exc_info=True)

    async def _fetch_portaler_data(self, guild_id: str, token: str) -> Optional[List]:
        """Fetch map data from Portaler API

        Returns an array of map objects from the API
        """
        url = f"https://portaler.app/api/map/list/{guild_id}?mergeWithPublic=true"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}"
        }

        log.debug(f"Fetching Portaler data for guild ID: {guild_id}")
        return await http_get(url, headers=headers)

    def _build_connection_graph(self, map_data: List, home_zone: str) -> List[str]:
        """Build a text representation of connections from home zone

        Args:
            map_data: Array of map objects from Portaler API
            home_zone: The zone to show connections from

        Returns:
            List of strings representing the connection graph
        """
        if not map_data:
            return ["No map data available"]

        # API returns an array of maps, iterate through all portal connections
        lines = [f"**Connections from {home_zone}:**", ""]

        found_connections = []

        # Iterate through all maps in the array
        for map_obj in map_data:
            portal_connections = map_obj.get("portalConnections", [])

            # Look for connections where fromZone matches our home zone
            for connection in portal_connections:
                info = connection.get("info", {})
                from_zone = info.get("fromZone", {})
                to_zone = info.get("toZone", {})

                from_zone_name = from_zone.get("name", "")

                # Check if this connection starts from our home zone
                if from_zone_name.lower() == home_zone.lower():
                    to_zone_name = to_zone.get("name", "Unknown")
                    to_zone_tier = to_zone.get("tier", "?")
                    to_zone_type = to_zone.get("type", "Unknown")
                    portal_type = info.get("portalType", "Unknown")
                    expiring_date = info.get("expiringDate", None)

                    # Calculate time remaining if expiring date is provided
                    time_str = "Unknown"
                    if expiring_date:
                        try:
                            # Parse ISO format datetime
                            expiry = datetime.fromisoformat(expiring_date.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            time_delta = expiry - now

                            if time_delta.total_seconds() > 0:
                                hours = int(time_delta.total_seconds() // 3600)
                                minutes = int((time_delta.total_seconds() % 3600) // 60)
                                time_str = f"{hours}h {minutes}m"
                            else:
                                time_str = "Expired"
                        except Exception as e:
                            log.warning(f"Failed to parse expiring date: {e}")
                            time_str = "Unknown"

                    found_connections.append({
                        "to_zone": to_zone_name,
                        "tier": to_zone_tier,
                        "type": to_zone_type,
                        "portal_type": portal_type,
                        "time_remaining": time_str
                    })

        if not found_connections:
            return [f"No connections found from {home_zone}"]

        # Build the connection list
        for i, conn in enumerate(found_connections, 1):
            lines.append(
                f"{i}. **{conn['to_zone']}** (T{conn['tier']} {conn['type']}) - "
                f"Portal: {conn['portal_type']} - Time: {conn['time_remaining']}"
            )

        return lines

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.group(name="setava")
    async def setava(self, ctx):
        """Configure Avalon road tracker settings"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @setava.command(name="token")
    async def setava_token(self, ctx, *, token: str):
        """Set the Portaler API bearer token

        The Discord server ID will be automatically used as the Portaler guild ID.
        Get your token from Portaler.app (check browser dev tools or Portaler documentation).

        Usage: [p]setava token <token>
        Example: [p]setava token your_bearer_token_here
        """
        # Use Discord guild ID as the Portaler guild ID
        guild_id = str(ctx.guild.id)

        # Store both token and guild_id
        await self.config.guild(ctx.guild).portaler_token.set(token)
        await self.config.guild(ctx.guild).portaler_guild_id.set(guild_id)
        log.debug(f"Set Portaler token for {ctx.guild.name} using Discord guild ID: {guild_id}")

        # Try to fetch data immediately to validate the token
        map_data = await self._fetch_portaler_data(guild_id, token)
        if map_data:
            await self.config.guild(ctx.guild).last_map_data.set(map_data)
            await ctx.send(
                f"✅ Portaler token set successfully! Using Discord server ID `{guild_id}` as Portaler guild ID.\n"
                "Data fetched and cached."
            )
        else:
            await ctx.send(
                f"⚠️ Portaler token set, but failed to fetch data.\n"
                f"Using Discord server ID: `{guild_id}`\n"
                "Please verify:\n"
                "1. Your token is correct\n"
                "2. The Discord server ID matches your Portaler guild ID\n"
                "3. You have access to the Portaler guild"
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
