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

    # Royal cities for prioritization
    ROYAL_CITIES = frozenset([
        "caerleon", "bridgewatch", "fort sterling",
        "lymhurst", "martlock", "thetford"
    ])

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=73602, force_registration=True)
        self.config.register_global(
            portaler_token=None,  # Global token for all API requests
        )
        self.config.register_guild(
            home_zone=None,
            last_map_data=None,  # Cache of last successful map data
            max_connections=10,  # Default max connections to display
            guild_ids=[],  # Complete list of guild IDs to query (not merged with server guild)
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
        """Fetch data for all guilds with configured guild IDs"""
        # Get the global token
        token = await self.config.portaler_token()

        if not token:
            log.debug("No global Portaler token configured")
            return

        for guild in self.bot.guilds:
            try:
                guild_ids = await self.config.guild(guild).guild_ids()

                if not guild_ids:
                    log.debug(f"No Portaler guild IDs configured for {guild.name}")
                    continue

                # Fetch data from all configured guild IDs
                all_map_data = []

                for portaler_guild_id in guild_ids:
                    try:
                        map_data = await self._fetch_portaler_data(portaler_guild_id, token)
                        if map_data:
                            all_map_data.append(map_data)
                            log.debug(f"Fetched data from guild {portaler_guild_id} for {guild.name}")
                    except Exception as e:
                        log.error(f"Error fetching data for guild {portaler_guild_id}: {e}", exc_info=True)

                # Merge all data (method handles single dataset case efficiently)
                if all_map_data:
                    merged_data = self._merge_all_map_data(all_map_data)
                    await self.config.guild(guild).last_map_data.set(merged_data)
                    log.debug(f"Updated data from {len(all_map_data)} guild(s) for {guild.name}")

            except Exception as e:
                log.error(f"Error fetching data for guild {guild.name}: {e}", exc_info=True)

    def _validate_guild_id(self, guild_id: str) -> tuple[bool, str]:
        """Validate a Portaler guild ID

        Args:
            guild_id: The guild ID string to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not guild_id.isdigit():
            return False, f"Invalid guild ID: `{guild_id}` (must be numeric)"
        if len(guild_id) < 17 or len(guild_id) > 20:
            return False, f"Invalid guild ID: `{guild_id}` (must be 17-20 digits)"
        return True, ""

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

    def _merge_all_map_data(self, all_data: List[List]) -> List:
        """Merge map data from multiple guilds efficiently

        Args:
            all_data: List of map data arrays from different guilds

        Returns:
            Merged array of map objects with combined portal connections
        """
        if not all_data:
            return []

        # Filter out None/empty entries
        valid_data = [data for data in all_data if data]

        if not valid_data:
            return []
        if len(valid_data) == 1:
            return valid_data[0]

        # Build a dictionary to track all connections by a unique key
        # Key format: "fromZone|toZone|portalType"
        connection_map = {}

        # Process all datasets in a single pass
        for map_data in valid_data:
            for map_obj in map_data:
                portal_connections = map_obj.get("portalConnections", [])
                for conn in portal_connections:
                    info = conn.get("info", {})
                    from_zone_name = info.get("fromZone", {}).get("name", "")
                    to_zone_name = info.get("toZone", {}).get("name", "")
                    portal_type = info.get("portalType", "")

                    key = f"{from_zone_name}|{to_zone_name}|{portal_type}"
                    # Store the connection, preferring newer expiry times
                    if key not in connection_map:
                        connection_map[key] = conn
                    else:
                        # Keep the connection with the later expiring date
                        existing_expiry = connection_map[key].get("info", {}).get("expiringDate", "")
                        new_expiry = info.get("expiringDate", "")
                        # ISO 8601 dates are lexicographically sortable
                        # Empty string means no expiry, so always replace with a dated entry
                        if new_expiry and (not existing_expiry or new_expiry > existing_expiry):
                            connection_map[key] = conn

        # Reconstruct the merged data structure
        merged_map = {
            "portalConnections": list(connection_map.values())
        }
        return [merged_map]

    def _build_connection_graph(self, map_data: List) -> dict:
        """Build a complete graph of all connections from the map data

        Args:
            map_data: Array of map objects from Portaler API

        Returns:
            Dictionary mapping from_zone -> list of (to_zone, connection_info) tuples
        """
        graph = {}

        for map_obj in map_data:
            portal_connections = map_obj.get("portalConnections", [])

            for connection in portal_connections:
                info = connection.get("info", {})
                from_zone = info.get("fromZone", {})
                to_zone = info.get("toZone", {})

                from_zone_name = from_zone.get("name", "")
                to_zone_name = to_zone.get("name", "")

                if not from_zone_name or not to_zone_name:
                    continue

                # Store connection info we'll need later
                conn_info = {
                    "to_zone": to_zone_name,
                    "tier": to_zone.get("tier", "?"),
                    "type": to_zone.get("type", "Unknown"),
                    "color": to_zone.get("color", "#888888"),
                    "portal_type": info.get("portalType", "Unknown"),
                    "expiring_date": info.get("expiringDate", None),
                }

                # Add to graph (adjacency list)
                if from_zone_name not in graph:
                    graph[from_zone_name] = []
                graph[from_zone_name].append(conn_info)

        return graph

    def _find_connection_chains(self, graph: dict, home_zone: str, max_depth: int = 5) -> List[List[dict]]:
        """Find all connection chains starting from home zone using BFS

        Args:
            graph: Connection graph from _build_connection_graph
            home_zone: Starting zone
            max_depth: Maximum chain length to explore

        Returns:
            List of chains, where each chain is a list of connection_info dicts
        """
        from collections import deque

        if home_zone not in graph:
            return []

        chains = []
        queue = deque()

        # Initialize with direct connections from home
        for conn in graph[home_zone]:
            queue.append([conn])

        while queue:
            current_chain = queue.popleft()
            last_zone = current_chain[-1]["to_zone"]

            # Add this chain to results
            chains.append(current_chain)

            # If we haven't reached max depth and this zone has outgoing connections
            if len(current_chain) < max_depth and last_zone in graph:
                # Build set of all zones already in this chain path
                # Include home zone and all destination zones in the chain
                chain_zones = {home_zone}
                chain_zones.update(conn["to_zone"] for conn in current_chain)

                for next_conn in graph[last_zone]:
                    next_zone = next_conn["to_zone"]
                    # Avoid cycles by checking if this zone is already in the path
                    if next_zone not in chain_zones:
                        # Create new chain with this connection added
                        new_chain = current_chain + [next_conn]
                        queue.append(new_chain)

        return chains

    def _get_connections_data(self, map_data: List, home_zone: str, max_connections: int = None) -> List[dict]:
        """Extract connection data from Portaler API response

        Args:
            map_data: Array of map objects from Portaler API
            home_zone: The zone to show connections from
            max_connections: Maximum number of connections to return (None for all)

        Returns:
            List of connection chain dictionaries, prioritized by royal cities and chain length
        """
        if not map_data:
            return []

        # Build complete connection graph
        graph = self._build_connection_graph(map_data)

        if not graph:
            return []

        # Find all chains from home zone
        chains = self._find_connection_chains(graph, home_zone, max_depth=5)

        if not chains:
            return []

        # Process chains into display format
        found_connections = []

        for chain in chains:
            # Get the final destination
            last_conn = chain[-1]
            final_zone = last_conn["to_zone"]

            # Calculate time remaining for the first connection in chain (most critical)
            first_conn = chain[0]
            time_str = self._calculate_time_remaining(first_conn.get("expiring_date"))

            # Determine priority
            # 1. Chains ending at royal cities (shorter chains preferred)
            # 2. Longer chains to non-royal destinations
            # 3. Shorter chains to non-royal destinations
            if final_zone.lower() in self.ROYAL_CITIES:
                priority = (1, len(chain))  # Royal city, prefer shorter
            else:
                priority = (2, -len(chain))  # Non-royal, prefer longer chains

            found_connections.append({
                "chain": chain,
                "final_zone": final_zone,
                "chain_length": len(chain),
                "tier": last_conn["tier"],
                "type": last_conn["type"],
                "color": last_conn["color"],
                "time_remaining": time_str,
                "priority": priority
            })

        # Sort by priority
        found_connections.sort(key=lambda x: (x["priority"], x["final_zone"].lower()))

        # Apply max_connections limit if specified
        if max_connections is not None and len(found_connections) > max_connections:
            found_connections = found_connections[:max_connections]

        return found_connections

    def _calculate_time_remaining(self, expiring_date: Optional[str]) -> str:
        """Calculate time remaining from an expiring date string

        Args:
            expiring_date: ISO 8601 formatted expiring date string

        Returns:
            Formatted time string (e.g., "2h 30m", "Expired", "Unknown")
        """
        if not expiring_date:
            return "Unknown"

        try:
            expiry = datetime.fromisoformat(expiring_date.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            time_delta = expiry - now

            if time_delta.total_seconds() > 0:
                hours = int(time_delta.total_seconds() // 3600)
                minutes = int((time_delta.total_seconds() % 3600) // 60)
                return f"{hours}h {minutes}m"
            else:
                return "Expired"
        except Exception as e:
            log.warning(f"Failed to parse expiring date: {e}")
            return "Unknown"

    def _generate_graph_image(self, home_zone: str, connections: List[dict]) -> io.BytesIO:
        """Generate a visual graph image showing full connection chains

        Args:
            home_zone: The home zone name
            connections: List of connection chain dictionaries

        Returns:
            BytesIO object containing the PNG image
        """
        # Calculate image dimensions based on content
        node_width = 120
        node_height = 60
        horizontal_spacing = 40
        vertical_spacing = 20
        margin = 80
        title_height = 80

        # Find the maximum chain length to determine width
        max_chain_length = max([len(conn.get('chain', [])) for conn in connections], default=0)
        # Total columns: home + chain zones
        total_columns = max_chain_length + 1

        width = max(1200, margin * 2 + total_columns * node_width + (total_columns - 1) * horizontal_spacing)
        height = max(600, title_height + len(connections) * (node_height + vertical_spacing) + margin)

        # Create image with dark background
        img = Image.new('RGB', (width, height), color='#2C2F33')
        draw = ImageDraw.Draw(img)

        # Try to use a reasonable font, fallback to default
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            node_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
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
            # Draw each chain horizontally
            for chain_idx, conn in enumerate(connections):
                chain = conn.get('chain', [])
                # Skip any connections with empty chains (shouldn't happen but protects against malformed data)
                if not chain:
                    continue

                # Calculate y position for this chain
                y = title_height + chain_idx * (node_height + vertical_spacing)

                # Build full zone list: [home_zone] + all zones in chain
                zones = [home_zone]
                for hop in chain:
                    zones.append(hop['to_zone'])

                # Draw nodes and connections for this chain
                for zone_idx, zone_name in enumerate(zones):
                    # Calculate x position
                    x = margin + zone_idx * (node_width + horizontal_spacing)

                    # Determine node color
                    if zone_idx == 0:
                        # Home zone - special color
                        node_color = '#7289DA'
                        zone_tier = ""
                        zone_type = ""
                    else:
                        # Get color from the hop that leads to this zone
                        hop = chain[zone_idx - 1]
                        node_color = hop.get('color', '#888888')
                        if not node_color.startswith('#'):
                            node_color = '#888888'
                        zone_tier = hop.get('tier', '?')
                        zone_type = hop.get('type', '')

                    # Check if this is a royal city
                    is_royal = zone_name.lower() in self.ROYAL_CITIES

                    # Draw node rectangle
                    node_x1 = x
                    node_y1 = y
                    node_x2 = x + node_width
                    node_y2 = y + node_height

                    # Add royal city indicator with gold outline
                    if is_royal:
                        draw.rectangle([node_x1, node_y1, node_x2, node_y2],
                                       fill=node_color, outline='#FFD700', width=3)
                    else:
                        draw.rectangle([node_x1, node_y1, node_x2, node_y2],
                                       fill=node_color, outline='#FFFFFF', width=2)

                    # Draw zone name (truncate if too long)
                    display_name = zone_name
                    if len(display_name) > 12:
                        display_name = display_name[:9] + "..."

                    text_y = y + node_height // 2
                    if zone_tier:
                        # Draw name above center, tier/type below
                        draw.text((x + node_width // 2, y + node_height // 2 - 8),
                                  display_name, fill='#FFFFFF', font=node_font, anchor="mm")
                        tier_text = f"T{zone_tier} {zone_type[:3]}"
                        draw.text((x + node_width // 2, y + node_height // 2 + 8),
                                  tier_text, fill='#FFFFFF', font=info_font, anchor="mm")
                    else:
                        # Just draw name centered
                        draw.text((x + node_width // 2, text_y),
                                  display_name, fill='#FFFFFF', font=node_font, anchor="mm")

                    # Draw arrow to next zone
                    if zone_idx < len(zones) - 1:
                        # Draw line from this node to next
                        line_start_x = node_x2
                        line_start_y = y + node_height // 2
                        line_end_x = x + node_width + horizontal_spacing
                        line_end_y = y + node_height // 2

                        draw.line([line_start_x, line_start_y, line_end_x, line_end_y],
                                  fill='#99AAB5', width=2)

                        # Draw arrowhead
                        arrow_size = 6
                        draw.polygon([
                            (line_end_x, line_end_y),
                            (line_end_x - arrow_size, line_end_y - arrow_size),
                            (line_end_x - arrow_size, line_end_y + arrow_size)
                        ], fill='#99AAB5')

                        # Draw time remaining for this connection
                        # Get the hop that leads from current zone to next zone
                        hop = chain[zone_idx]
                        time_str = self._calculate_time_remaining(hop.get('expiring_date'))
                        time_text = f"⏱ {time_str}"
                        
                        # Position time text in the middle of the arrow
                        time_x = line_start_x + horizontal_spacing // 2
                        time_y = y + node_height // 2 - 10
                        draw.text((time_x, time_y), time_text, fill='#FFFF00',
                                  font=info_font, anchor="mm")

        # Save to BytesIO
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

    def _build_connection_text(self, connections: List[dict], home_zone: str) -> List[str]:
        """Build a text representation of connections

        Args:
            connections: List of connection chain dictionaries
            home_zone: The home zone name

        Returns:
            List of strings representing the connections
        """
        if not connections:
            return [f"No connections found from {home_zone}"]

        lines = [f"**Connections from {home_zone}:**", ""]

        # Build the connection list showing full chains
        for i, conn in enumerate(connections, 1):
            chain = conn.get("chain", [])

            if not chain:
                continue

            # Build the chain string: Home -> Zone A -> Zone B -> Final
            chain_parts = [home_zone]
            for hop in chain:
                chain_parts.append(hop["to_zone"])

            chain_str = " → ".join(chain_parts)

            # Get info about the final destination
            final_zone = conn["final_zone"]
            is_royal = final_zone.lower() in self.ROYAL_CITIES
            royal_marker = " 👑" if is_royal else ""

            lines.append(
                f"{i}. {chain_str}{royal_marker} "
                f"(T{conn['tier']} {conn['type']}) - "
                f"Time: {conn['time_remaining']}"
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
    async def setava_token(self, ctx, *, token: str):
        """Set the Portaler API bearer token globally (DM only for security)

        This command must be used in a DM to keep your token secure.
        Get your token from Portaler.app (check browser dev tools or Portaler documentation).
        The token will be used for all Portaler API requests across all servers.

        Usage: [p]setava token <token>
        Example: [p]setava token eyJhbGci...

        Note: Only bot owners can set the global token.
        """
        # Check if user is bot owner
        if not await self.bot.is_owner(ctx.author):
            await ctx.send(
                "❌ Only the bot owner can set the global Portaler token."
            )
            return

        # Store the token globally
        await self.config.portaler_token.set(token)
        log.debug(f"Set global Portaler token via DM from {ctx.author}")

        await ctx.send(
            "✅ Portaler token set successfully!\n"
            "The token will be used for all Portaler API requests across all servers.\n"
            "Use `[p]setava guilds <guild_id> ...` in each server to configure which Portaler guilds to query."
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

    @setava.command(name="connections")
    @commands.guild_only()
    async def setava_connections(self, ctx, number: int):
        """Set the maximum number of connections to display

        Sets how many connections should be shown from your home zone.
        The cog will prioritize showing connections to royal cities and portal rooms.

        Usage: [p]setava connections <number>
        Example: [p]setava connections 15
        """
        if number < 1:
            await ctx.send("❌ Number of connections must be at least 1")
            return

        if number > 50:
            await ctx.send("❌ Number of connections cannot exceed 50")
            return

        await self.config.guild(ctx.guild).max_connections.set(number)
        log.debug(f"Set max connections to {number} for {ctx.guild.name}")
        await ctx.send(f"✅ Maximum connections set to **{number}**")

    @setava.command(name="guilds")
    @commands.guild_only()
    async def setava_guilds(self, ctx, *guild_ids: str):
        """Set Portaler guild IDs to query for this server

        Specify ALL Portaler guild IDs you want to query. This is the complete list,
        not additional guilds. Connection data from all specified guilds will be merged together.
        Use this command without arguments to clear all guild IDs.

        Usage: [p]setava guilds <guild_id> [<guild_id> ...]
        Example: [p]setava guilds 123456 789012 345678

        To clear all guild IDs: [p]setava guilds
        """
        if not guild_ids:
            # Clear all guild IDs
            await self.config.guild(ctx.guild).guild_ids.set([])
            log.debug(f"Cleared all Portaler guild IDs for {ctx.guild.name}")
            await ctx.send("✅ Cleared all Portaler guild IDs")
            return

        # Validate and store guild IDs
        valid_ids = []
        for guild_id in guild_ids:
            is_valid, error_msg = self._validate_guild_id(guild_id)
            if not is_valid:
                await ctx.send(f"⚠️ {error_msg}")
                continue
            valid_ids.append(guild_id)

        if not valid_ids:
            await ctx.send("❌ No valid guild IDs provided")
            return

        await self.config.guild(ctx.guild).guild_ids.set(valid_ids)
        log.debug(f"Set Portaler guild IDs to {valid_ids} for {ctx.guild.name}")

        guilds_str = ", ".join([f"`{gid}`" for gid in valid_ids])
        await ctx.send(
            f"✅ Set Portaler guild IDs: {guilds_str}\n"
            f"Connection data from these {len(valid_ids)} guild(s) will be fetched and merged.\n"
            f"Note: A global token must be configured by the bot owner using `[p]setava token` in DM."
        )

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
            max_connections = await self.config.guild(ctx.guild).max_connections()

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
            connections = self._get_connections_data(map_data, home_zone, max_connections)

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

        Generates an image showing ALL Roads of Avalon connections from your home zone.
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

            # Get ALL connections data (no limit for image rendering)
            connections = self._get_connections_data(map_data, home_zone, max_connections=None)

            # Generate graph image
            try:
                image_bytes = self._generate_graph_image(home_zone, connections)
                file = discord.File(image_bytes, filename="avalon_connections.png")
                await ctx.send(file=file)
            except Exception as e:
                log.error(f"Error generating graph image: {e}", exc_info=True)
                await ctx.send(f"❌ Failed to generate graph image: {e}")
