import asyncio
import io
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional

import discord
import httpx
from PIL import Image, ImageDraw, ImageFont
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

    def _get_connections_data(self, map_data: List, home_zone: str) -> List[dict]:
        """Extract connection data from Portaler API response

        Args:
            map_data: Array of map objects from Portaler API
            home_zone: The zone to show connections from

        Returns:
            List of connection dictionaries
        """
        if not map_data:
            return []

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
                    to_zone_color = to_zone.get("color", "#888888")
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
                        "color": to_zone_color,
                        "portal_type": portal_type,
                        "time_remaining": time_str
                    })

        return found_connections

    def _generate_graph_image(self, home_zone: str, connections: List[dict]) -> io.BytesIO:
        """Generate a visual graph image showing connections

        Args:
            home_zone: The home zone name
            connections: List of connection dictionaries

        Returns:
            BytesIO object containing the PNG image
        """
        # Image dimensions
        width = 1200
        height = 800

        # Create image with dark background
        img = Image.new('RGB', (width, height), color='#2C2F33')
        draw = ImageDraw.Draw(img)

        # Try to use a reasonable font, fallback to default
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            node_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            title_font = ImageFont.load_default()
            node_font = ImageFont.load_default()
            info_font = ImageFont.load_default()

        # Draw title
        title = f"Roads of Avalon - Connections from {home_zone}"
        draw.text((width // 2, 40), title, fill='#FFFFFF', font=title_font, anchor="mm")

        if not connections:
            # Draw "no connections" message
            draw.text((width // 2, height // 2), "No connections found",
                      fill='#99AAB5', font=node_font, anchor="mm")
        else:
            # Calculate positions for nodes
            center_x = width // 2
            center_y = height // 2

            # Home zone in the center
            home_radius = 60
            draw.ellipse([center_x - home_radius, center_y - home_radius,
                          center_x + home_radius, center_y + home_radius],
                         fill='#7289DA', outline='#FFFFFF', width=3)
            draw.text((center_x, center_y), home_zone, fill='#FFFFFF',
                      font=node_font, anchor="mm")

            # Position connected zones in a circle around the home zone
            num_connections = len(connections)
            orbit_radius = 250
            angle_step = 2 * math.pi / num_connections

            for i, conn in enumerate(connections):
                # Calculate position
                angle = i * angle_step - math.pi / 2  # Start from top
                x = center_x + int(orbit_radius * math.cos(angle))
                y = center_y + int(orbit_radius * math.sin(angle))

                # Get zone color (convert hex to RGB if needed)
                zone_color = conn['color']
                if zone_color.startswith('#'):
                    zone_color = zone_color
                else:
                    zone_color = '#888888'

                # Draw connection line
                draw.line([center_x, center_y, x, y], fill='#99AAB5', width=2)

                # Draw zone node
                node_radius = 50
                draw.ellipse([x - node_radius, y - node_radius,
                              x + node_radius, y + node_radius],
                             fill=zone_color, outline='#FFFFFF', width=2)

                # Draw zone name
                zone_name = conn['to_zone']
                if len(zone_name) > 15:
                    zone_name = zone_name[:12] + "..."
                draw.text((x, y - 10), zone_name, fill='#FFFFFF',
                          font=info_font, anchor="mm")

                # Draw tier and type
                tier_type = f"T{conn['tier']} {conn['type'][:3]}"
                draw.text((x, y + 5), tier_type, fill='#FFFFFF',
                          font=info_font, anchor="mm")

                # Draw time remaining
                draw.text((x, y + 20), conn['time_remaining'], fill='#FFFF00',
                          font=info_font, anchor="mm")

                # Draw portal type badge near the line
                mid_x = center_x + int((orbit_radius / 2) * math.cos(angle))
                mid_y = center_y + int((orbit_radius / 2) * math.sin(angle))
                portal_text = conn['portal_type'][:3].upper()

                # Draw background for portal type
                bbox = draw.textbbox((mid_x, mid_y), portal_text, font=info_font, anchor="mm")
                draw.rectangle([bbox[0]-2, bbox[1]-2, bbox[2]+2, bbox[3]+2],
                               fill='#23272A', outline='#7289DA')
                draw.text((mid_x, mid_y), portal_text, fill='#7289DA',
                          font=info_font, anchor="mm")

        # Save to BytesIO
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

    def _build_connection_text(self, connections: List[dict], home_zone: str) -> List[str]:
        """Build a text representation of connections

        Args:
            connections: List of connection dictionaries
            home_zone: The home zone name

        Returns:
            List of strings representing the connections
        """
        if not connections:
            return [f"No connections found from {home_zone}"]

        lines = [f"**Connections from {home_zone}:**", ""]

        # Build the connection list
        for i, conn in enumerate(connections, 1):
            lines.append(
                f"{i}. **{conn['to_zone']}** (T{conn['tier']} {conn['type']}) - "
                f"Portal: {conn['portal_type']} - Time: {conn['time_remaining']}"
            )

        return lines

    @checks.admin_or_permissions(manage_guild=True)
    @commands.group(name="setava")
    async def setava(self, ctx):
        """Configure Avalon road tracker settings"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @setava.command(name="token")
    @commands.dm_only()
    async def setava_token(self, ctx, guild_id: str, *, token: str):
        """Set the Portaler API bearer token (DM only for security)

        This command must be used in a DM to keep your token secure.
        Get your token from Portaler.app (check browser dev tools or Portaler documentation).

        Usage: [p]setava token <token> <guild_id>
        Example: [p]setava token eyJhbGci... 123456789012345678

        The guild_id is your Discord server's ID (enable Developer Mode in Discord settings,
        right-click your server icon, and select "Copy Server ID").
        """
        # Validate that the bot is in the guild
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            await ctx.send(
                f"❌ I'm not in a server with ID `{guild_id}`.\n"
                "Please check the guild ID and make sure I'm a member of that server."
            )
            return

        # Check if the user is an admin in that guild
        member = guild.get_member(ctx.author.id)
        if not member:
            await ctx.send(
                f"❌ You are not a member of the server with ID `{guild_id}`."
            )
            return

        # Check if user has admin permissions
        if not (member.guild_permissions.administrator or
                member.guild_permissions.manage_guild or
                await self.bot.is_owner(ctx.author)):
            await ctx.send(
                f"❌ You don't have administrator or manage server permissions in **{guild.name}**."
            )
            return

        # Store both token and guild_id
        await self.config.guild(guild).portaler_token.set(token)
        await self.config.guild(guild).portaler_guild_id.set(guild_id)
        log.debug(f"Set Portaler token for {guild.name} (ID: {guild_id}) via DM from {ctx.author}")

        # Try to fetch data immediately to validate the token
        map_data = await self._fetch_portaler_data(guild_id, token)
        if map_data:
            await self.config.guild(guild).last_map_data.set(map_data)
            await ctx.send(
                f"✅ Portaler token set successfully for **{guild.name}** (ID: `{guild_id}`)!\n"
                "Data fetched and cached."
            )
        else:
            await ctx.send(
                f"⚠️ Portaler token set for **{guild.name}**, but failed to fetch data.\n"
                f"Using guild ID: `{guild_id}`\n"
                "Please verify:\n"
                "1. Your token is correct\n"
                "2. The guild ID is correct\n"
                "3. You have access to the Portaler guild"
            )

    @setava.command(name="home")
    @commands.guild_only()
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
    @commands.group(name="ava", invoke_without_command=True)
    async def ava(self, ctx):
        """Display connections from the home zone (text format)

        Shows current Roads of Avalon connections from your configured home zone.
        Use `[p]ava image` for a visual graph representation.
        """
        if ctx.invoked_subcommand is None:
            await self._display_ava_text(ctx)

    async def _display_ava_text(self, ctx):
        """Display connections in text format"""
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
                    "`[p]setava token <token>`, or wait for the next data refresh."
                )
                return

            # Get connections data
            connections = self._get_connections_data(map_data, home_zone)

            # Build connection text
            graph_lines = self._build_connection_text(connections, home_zone)
            graph_text = "\n".join(graph_lines)

            # Send the text
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

    @ava.command(name="image")
    async def ava_image(self, ctx):
        """Display connections as a visual graph image

        Generates an image showing Roads of Avalon connections from your home zone.
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
                    "`[p]setava token <token>`, or wait for the next data refresh."
                )
                return

            # Get connections data
            connections = self._get_connections_data(map_data, home_zone)

            # Generate graph image
            try:
                image_bytes = self._generate_graph_image(home_zone, connections)
                file = discord.File(image_bytes, filename="avalon_connections.png")
                await ctx.send(file=file)
            except Exception as e:
                log.error(f"Error generating graph image: {e}", exc_info=True)
                await ctx.send(f"❌ Failed to generate graph image: {e}")
