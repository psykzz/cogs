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
            max_connections=10,  # Default max connections to display
            guild_ids=[],  # Complete list of guild IDs to query (not merged with server guild)
        )

    async def _fetch_guild_data(self, guild):
        """Fetch and merge data for a specific guild's configured Portaler guild IDs

        Args:
            guild: Discord guild object

        Returns:
            Merged map data from all configured guild IDs, or None if no data available
        """
        # Get the global token
        token = await self.config.portaler_token()

        if not token:
            log.debug("No global Portaler token configured")
            return None

        guild_ids = await self.config.guild(guild).guild_ids()

        if not guild_ids:
            log.debug(f"No Portaler guild IDs configured for {guild.name}")
            return None

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
            log.debug(f"Merged data from {len(all_map_data)} guild(s) for {guild.name}")
            return merged_data

        return None

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

    def _build_graph_tree(self, connections: List[dict], home_zone: str) -> dict:
        """Build a tree structure from connection chains for graph visualization

        Args:
            connections: List of connection chain dictionaries
            home_zone: The home zone name

        Returns:
            Tree structure with nodes containing: {
                'name': zone_name,
                'children': [child_nodes],
                'info': connection_info (tier, type, color, time),
                'is_royal': bool
            }
        """
        # Build tree structure
        root = {
            'name': home_zone,
            'children': [],
            'info': None,
            'is_royal': home_zone.lower() in self.ROYAL_CITIES
        }
        
        for conn in connections:
            chain = conn.get('chain', [])
            if not chain:
                continue
            
            # Traverse/build the tree for this chain
            current = root
            for hop_idx, hop in enumerate(chain):
                zone_name = hop['to_zone']
                
                # Check if this child already exists
                child_node = None
                for child in current['children']:
                    if child['name'] == zone_name:
                        child_node = child
                        break
                
                # Create new child if it doesn't exist
                if child_node is None:
                    child_node = {
                        'name': zone_name,
                        'children': [],
                        'info': {
                            'tier': hop.get('tier', '?'),
                            'type': hop.get('type', 'Unknown'),
                            'color': hop.get('color', '#888888'),
                            'time': self._calculate_time_remaining(hop.get('expiring_date'))
                        },
                        'is_royal': zone_name.lower() in self.ROYAL_CITIES
                    }
                    current['children'].append(child_node)
                
                current = child_node
        
        return root

    def _calculate_tree_positions(self, root: dict, node_width: int, node_height: int,
                                  horizontal_spacing: int, vertical_spacing: int,
                                  start_x: int, start_y: int) -> tuple:
        """Calculate positions for all nodes in the tree using a hierarchical layout

        Args:
            root: Tree root node
            node_width, node_height: Node dimensions
            horizontal_spacing, vertical_spacing: Spacing between nodes
            start_x, start_y: Starting position

        Returns:
            Tuple of (positions dict, max_x, max_y) where positions maps node_id -> (x, y, node_data)
        """
        positions = {}
        
        def assign_positions(node, depth, y_offset):
            """Recursively assign positions using depth-first traversal"""
            # Calculate x position based on depth
            x = start_x + depth * (node_width + horizontal_spacing)
            y = y_offset
            
            # Store position with unique key (name + depth to handle duplicate zone names at different depths)
            node_id = f"{node['name']}_{depth}_{y}"
            positions[node_id] = (x, y, node)
            
            # Process children
            current_y = y_offset
            for child in node['children']:
                child_id = assign_positions(child, depth + 1, current_y)
                current_y += node_height + vertical_spacing
            
            return node_id
        
        # Start positioning from root
        assign_positions(root, 0, start_y)
        
        # Calculate bounds
        max_x = max((pos[0] for pos in positions.values()), default=start_x) + node_width
        max_y = max((pos[1] for pos in positions.values()), default=start_y) + node_height
        
        return positions, max_x, max_y

    def _generate_graph_image(self, home_zone: str, connections: List[dict]) -> io.BytesIO:
        """Generate a visual graph image showing connected nodes (tree structure)

        Args:
            home_zone: The home zone name
            connections: List of connection chain dictionaries

        Returns:
            BytesIO object containing the PNG image
        """
        # Node and spacing configuration
        node_width = 120
        node_height = 60
        horizontal_spacing = 40
        vertical_spacing = 20
        margin = 80
        title_height = 80

        # Try to use a reasonable font, fallback to default
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            node_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
        except Exception:
            title_font = ImageFont.load_default()
            node_font = ImageFont.load_default()
            info_font = ImageFont.load_default()

        if not connections:
            # Create minimal image for no connections
            width = 1200
            height = 600
            img = Image.new('RGB', (width, height), color='#2C2F33')
            draw = ImageDraw.Draw(img)
            
            title = f"Roads of Avalon - Connections from {home_zone}"
            draw.text((width // 2, 40), title, fill='#FFFFFF', font=title_font, anchor="mm")
            draw.text((width // 2, height // 2), "No connections found",
                      fill='#99AAB5', font=node_font, anchor="mm")
        else:
            # Build tree structure from connections
            tree = self._build_graph_tree(connections, home_zone)
            
            # Calculate node positions
            positions, max_x, max_y = self._calculate_tree_positions(
                tree, node_width, node_height, horizontal_spacing, vertical_spacing,
                margin, title_height
            )
            
            # Calculate image size
            width = max(1200, max_x + margin)
            height = max(600, max_y + margin)
            
            # Create image with dark background
            img = Image.new('RGB', (width, height), color='#2C2F33')
            draw = ImageDraw.Draw(img)
            
            # Draw title
            title = f"Roads of Avalon - Connections from {home_zone}"
            draw.text((width // 2, 40), title, fill='#FFFFFF', font=title_font, anchor="mm")
            
            # Draw edges first (so they appear behind nodes)
            # Build a lookup for quick position finding
            pos_by_name_depth = {}
            for node_id, (x, y, node_data) in positions.items():
                # Extract depth from node_id format: "name_depth_y"
                parts = node_id.rsplit('_', 2)
                name = '_'.join(parts[:-2]) if len(parts) > 2 else parts[0]
                depth = int(parts[-2]) if len(parts) > 2 else 0
                key = f"{name}_{depth}"
                if key not in pos_by_name_depth:
                    pos_by_name_depth[key] = []
                pos_by_name_depth[key].append((x, y, node_id, node_data))
            
            # Draw edges from parents to children
            for node_id, (parent_x, parent_y, parent_node) in positions.items():
                parts = node_id.rsplit('_', 2)
                parent_depth = int(parts[-2]) if len(parts) > 2 else 0
                
                for child in parent_node['children']:
                    child_depth = parent_depth + 1
                    child_key = f"{child['name']}_{child_depth}"
                    
                    # Find the matching child position
                    if child_key in pos_by_name_depth:
                        for child_x, child_y, child_id, child_data in pos_by_name_depth[child_key]:
                            # Verify this is actually a child of this specific parent instance
                            # by checking if the y-coordinate is within range
                            if abs(child_y - parent_y) <= (node_height + vertical_spacing) * 10:
                                # Draw edge from parent to child
                                line_start_x = parent_x + node_width
                                line_start_y = parent_y + node_height // 2
                                line_end_x = child_x
                                line_end_y = child_y + node_height // 2
                                
                                draw.line([line_start_x, line_start_y, line_end_x, line_end_y],
                                         fill='#99AAB5', width=2)
                                
                                # Draw arrowhead
                                arrow_size = 6
                                draw.polygon([
                                    (line_end_x, line_end_y),
                                    (line_end_x - arrow_size, line_end_y - arrow_size),
                                    (line_end_x - arrow_size, line_end_y + arrow_size)
                                ], fill='#99AAB5')
                                
                                # Draw time remaining on the edge
                                if child['info']:
                                    time_str = child['info']['time']
                                    time_text = f"⏱ {time_str}"
                                    time_x = (line_start_x + line_end_x) // 2
                                    time_y = (line_start_y + line_end_y) // 2 - 10
                                    draw.text((time_x, time_y), time_text, fill='#FFFF00',
                                             font=info_font, anchor="mm")
                                break
            
            # Draw nodes on top of edges
            for node_id, (x, y, node_data) in positions.items():
                zone_name = node_data['name']
                is_royal = node_data['is_royal']
                info = node_data['info']
                
                # Determine node color
                if info is None:
                    # Home zone - special color
                    node_color = '#7289DA'
                    zone_tier = ""
                    zone_type = ""
                else:
                    node_color = info.get('color', '#888888')
                    if not node_color.startswith('#'):
                        node_color = '#888888'
                    zone_tier = info.get('tier', '?')
                    zone_type = info.get('type', '')
                
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

        # Save to BytesIO
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

    def _build_connection_text(self, connections: List[dict], home_zone: str) -> List[str]:
        """Build a text representation of connections with grouped common prefixes

        Args:
            connections: List of connection chain dictionaries
            home_zone: The home zone name

        Returns:
            List of strings representing the connections
        """
        if not connections:
            return [f"No connections found from {home_zone}"]

        lines = [f"**Connections from {home_zone}:**", ""]

        # Group connections by their chain prefix
        i = 0
        while i < len(connections):
            current_conn = connections[i]
            current_chain = current_conn.get("chain", [])
            
            if not current_chain:
                i += 1
                continue

            # Build the chain parts for current connection
            chain_parts = [home_zone]
            for hop in current_chain:
                chain_parts.append(hop["to_zone"])

            # Find all connections that share the same prefix (all but last zone)
            prefix = chain_parts[:-1]  # Everything except the final destination
            grouped = [current_conn]
            
            # Look ahead to find connections with the same prefix
            j = i + 1
            while j < len(connections):
                next_conn = connections[j]
                next_chain = next_conn.get("chain", [])
                
                if not next_chain:
                    j += 1
                    continue
                
                # Build chain parts for next connection
                next_parts = [home_zone]
                for hop in next_chain:
                    next_parts.append(hop["to_zone"])
                
                # Check if this connection shares the same prefix
                next_prefix = next_parts[:-1]
                if len(next_prefix) == len(prefix) and next_prefix == prefix:
                    grouped.append(next_conn)
                    j += 1
                else:
                    break
            
            # Now output the grouped connections
            if len(grouped) == 1:
                # Single connection, show full path
                conn = grouped[0]
                chain_str = " → ".join(chain_parts)
                
                final_zone = conn["final_zone"]
                is_royal = final_zone.lower() in self.ROYAL_CITIES
                royal_marker = " 👑" if is_royal else ""
                
                lines.append(
                    f"{chain_str}{royal_marker} "
                    f"(T{conn['tier']} {conn['type']}) - "
                    f"Time: {conn['time_remaining']}"
                )
            else:
                # Multiple connections with same prefix, show prefix once
                prefix_str = " → ".join(prefix)
                
                for idx, conn in enumerate(grouped):
                    final_zone = conn["final_zone"]
                    is_royal = final_zone.lower() in self.ROYAL_CITIES
                    royal_marker = " 👑" if is_royal else ""
                    
                    if idx == 0:
                        # First line shows full prefix
                        lines.append(
                            f"{prefix_str} → {final_zone}{royal_marker} "
                            f"(T{conn['tier']} {conn['type']}) - "
                            f"Time: {conn['time_remaining']}"
                        )
                    else:
                        # Subsequent lines show only the final zone with indentation
                        indent = " " * len(prefix_str)
                        lines.append(
                            f"{indent} → {final_zone}{royal_marker} "
                            f"(T{conn['tier']} {conn['type']}) - "
                            f"Time: {conn['time_remaining']}"
                        )
            
            # Add blank line between groups for readability
            lines.append("")
            
            # Move to next group
            i = j if j > i + 1 else i + 1

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
            max_connections = await self.config.guild(ctx.guild).max_connections()

            if not home_zone:
                await ctx.send(
                    "❌ No home zone configured. Use `[p]setava home <zone>` to set one."
                )
                return

            # Fetch data on-demand
            map_data = await self._fetch_guild_data(ctx.guild)

            if not map_data:
                await ctx.send(
                    "❌ No map data available. Please ensure your Portaler token is configured with "
                    "`[p]setava token <token>`, and that guild IDs are set with `[p]setava guilds <id> ...`."
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
            max_connections = await self.config.guild(ctx.guild).max_connections()

            if not home_zone:
                await ctx.send(
                    "❌ No home zone configured. Use `[p]setava home <zone>` to set one."
                )
                return

            # Fetch data on-demand
            map_data = await self._fetch_guild_data(ctx.guild)

            if not map_data:
                await ctx.send(
                    "❌ No map data available. Please ensure your Portaler token is configured with "
                    "`[p]setava token <token>`, and that guild IDs are set with `[p]setava guilds <id> ...`."
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
