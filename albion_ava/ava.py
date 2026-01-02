import asyncio
import io
import logging
import math
from datetime import datetime, timezone, timedelta
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

    # Valid Albion servers
    VALID_SERVERS = ["AMERICA", "ASIA", "EUROPE"]

    # Royal cities for prioritization
    ROYAL_CITIES = frozenset([
        "caerleon", "bridgewatch", "fort sterling",
        "lymhurst", "martlock", "thetford"
    ])

    # Zone color classification constants
    ZONE_COLORS = {
        'yellow': ['#ffff00', '#ffd700', '#ffeb3b', '#ffc107'],
        'blue': ['#0000ff', '#2196f3', '#1976d2'],
        'red': ['#ff0000', '#f44336', '#e91e63', '#ff5722'],
        'black': ['#000000', '#212121', '#424242']
    }

    # RGB thresholds for color classification
    RGB_YELLOW_MIN_RG = 200  # Minimum red and green for yellow
    RGB_YELLOW_MAX_B = 100   # Maximum blue for yellow
    RGB_BLUE_MIN_B = 150     # Minimum blue for blue zones
    RGB_BLUE_MAX_R = 100     # Maximum red for blue zones
    RGB_BLUE_MAX_G = 150     # Maximum green for blue zones
    RGB_RED_MIN_R = 200      # Minimum red for red zones
    RGB_RED_MAX_GB = 100     # Maximum green/blue for red zones
    RGB_BLACK_MAX_ALL = 50   # Maximum RGB values for black zones

    # Manual connection duration constraints
    MIN_DURATION_HOURS = 1   # Minimum duration for manual connections
    MAX_DURATION_HOURS = 24  # Maximum duration for manual connections

    def _classify_zone_color(self, color: str, zone_type: str) -> str:
        """Classify a zone based on its color code and type
        
        Args:
            color: Hex color code from the zone data
            zone_type: Zone type string from the zone data
            
        Returns:
            String classification: 'yellow', 'blue', 'black', 'red', 'road', or 'unknown'
        """
        if not color or not color.startswith('#'):
            return 'unknown'
        
        color_lower = color.lower()
        
        # Check against known color lists
        for zone_class, color_list in self.ZONE_COLORS.items():
            if color_lower in color_list:
                return zone_class
        
        # Check by RGB values for more flexibility
        try:
            # Remove # and parse hex (validate length first)
            hex_color = color_lower.lstrip('#')
            if len(hex_color) != 6:
                # Handle short hex codes by padding or rejecting
                return 'unknown'
            
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            
            # Yellow: high red and green, low blue
            if r > self.RGB_YELLOW_MIN_RG and g > self.RGB_YELLOW_MIN_RG and b < self.RGB_YELLOW_MAX_B:
                return 'yellow'
            
            # Blue: high blue, low red and green
            if b > self.RGB_BLUE_MIN_B and r < self.RGB_BLUE_MAX_R and g < self.RGB_BLUE_MAX_G:
                return 'blue'
            
            # Red: high red, low green and blue
            if r > self.RGB_RED_MIN_R and g < self.RGB_RED_MAX_GB and b < self.RGB_RED_MAX_GB:
                return 'red'
            
            # Black: all low values
            if r < self.RGB_BLACK_MAX_ALL and g < self.RGB_BLACK_MAX_ALL and b < self.RGB_BLACK_MAX_ALL:
                return 'black'
        except (ValueError, IndexError):
            pass
        
        # Check zone type for additional hints
        zone_type_lower = zone_type.lower() if zone_type else ''
        if 'road' in zone_type_lower or 'tunnel' in zone_type_lower:
            return 'road'
        
        return 'unknown'

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
            manual_connections=[],  # List of manually added connections
            server="EUROPE",  # Albion server to filter data by (AMERICA, ASIA, EUROPE)
        )

    def _create_manual_connection_object(self, from_zone: str, to_zone: str, duration_hours: int = 4):
        """Create a connection object in the Portaler API format for manual connections

        Args:
            from_zone: The starting zone name
            to_zone: The destination zone name
            duration_hours: Duration in hours (default 4)

        Returns:
            Connection object compatible with Portaler API format
        """
        # Calculate expiring date in ISO 8601 format with 'Z' suffix
        expiring_date = (datetime.now(timezone.utc).replace(microsecond=0) + 
                        timedelta(hours=duration_hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        return {
            "info": {
                "fromZone": {
                    "name": from_zone,
                    "tier": "?",
                    "type": "Manual",
                    "color": "#888888"
                },
                "toZone": {
                    "name": to_zone,
                    "tier": "?",
                    "type": "Manual",
                    "color": "#888888"
                },
                "portalType": "Manual",
                "expiringDate": expiring_date
            }
        }

    def _convert_manual_connections_to_map_data(self, manual_connections: list):
        """Convert manual connections to Portaler API map data format

        Args:
            manual_connections: List of manual connection entries

        Returns:
            Map data array compatible with Portaler API format
        """
        if not manual_connections:
            return []
        
        portal_connections = []
        for manual_conn in manual_connections:
            conn_obj = self._create_manual_connection_object(
                manual_conn['from_zone'],
                manual_conn['to_zone'],
                manual_conn.get('duration_hours', 4)
            )
            portal_connections.append(conn_obj)
        
        return [{
            "portalConnections": portal_connections
        }]

    async def _fetch_guild_data(self, guild):
        """Fetch and merge data for a specific guild's configured Portaler guild IDs

        Args:
            guild: Discord guild object

        Returns:
            Merged map data from all configured guild IDs and manual connections, 
            or None if no data available
        """
        # Get the global token
        token = await self.config.portaler_token()

        guild_ids = await self.config.guild(guild).guild_ids()
        server = await self.config.guild(guild).server()

        # Fetch data from all configured guild IDs
        all_map_data = []

        if token and guild_ids:
            for portaler_guild_id in guild_ids:
                try:
                    map_data = await self._fetch_portaler_data(portaler_guild_id, token)
                    if map_data:
                        # Filter by server - only keep data matching the configured server
                        filtered_data = self._filter_by_server(map_data, server)
                        if filtered_data:
                            # Count connections from this guild
                            connection_count = 0
                            for map_obj in filtered_data:
                                connection_count += len(map_obj.get("portalConnections", []))
                            
                            all_map_data.append(filtered_data)
                            log.info(f"Fetched {connection_count} connections from guild {portaler_guild_id} for {guild.name} (server: {server})")
                        else:
                            log.warning(f"No data for server {server} from guild {portaler_guild_id} for {guild.name}")
                    else:
                        log.warning(f"No data returned from guild {portaler_guild_id} for {guild.name}")
                except Exception as e:
                    log.error(f"Error fetching data for guild {portaler_guild_id}: {e}", exc_info=True)
        else:
            log.debug("No token or guild IDs configured, skipping API data fetch")

        # Get manual connections from config
        manual_connections = await self.config.guild(guild).manual_connections()
        if manual_connections:
            manual_map_data = self._convert_manual_connections_to_map_data(manual_connections)
            if manual_map_data:
                all_map_data.append(manual_map_data)
                log.info(f"Added {len(manual_connections)} manual connections for {guild.name}")

        # Merge all data (method handles single dataset case efficiently)
        if all_map_data:
            merged_data = self._merge_all_map_data(all_map_data)
            # Count total connections in merged data
            total_connections = 0
            for map_obj in merged_data:
                total_connections += len(map_obj.get("portalConnections", []))
            log.info(f"Merged data from {len(all_map_data)} source(s) for {guild.name}: {total_connections} total connections")
            return merged_data
        else:
            log.warning(f"No data available from any source for {guild.name}")

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

    def _filter_by_server(self, map_data: List, server: str) -> Optional[List]:
        """Filter map data to only include entries matching the specified server

        Args:
            map_data: Array of map objects from Portaler API
            server: Server name to filter by (AMERICA, ASIA, EUROPE)

        Returns:
            Filtered map data array, or None if no matching data
        """
        if not map_data:
            return None

        filtered_data = []
        for map_obj in map_data:
            # Check if this map object has an albionServer field
            albion_server = map_obj.get("albionServer")
            if albion_server and albion_server == server:
                filtered_data.append(map_obj)
            elif not albion_server:
                # If no albionServer field, include it (for backward compatibility)
                log.debug("Map object missing albionServer field, including by default")
                filtered_data.append(map_obj)

        return filtered_data if filtered_data else None

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

    def _make_connection_info(self, dest_name: str, zone_obj: dict, portal_info: dict) -> dict:
        """Create a connection info dictionary

        Args:
            dest_name: Destination zone name (original case)
            zone_obj: Zone object from API containing tier, type, color
            portal_info: Portal info object containing portal type and expiring date

        Returns:
            Connection info dictionary
        """
        return {
            "to_zone": dest_name,
            "tier": zone_obj.get("tier", "?"),
            "type": zone_obj.get("type", "Unknown"),
            "color": zone_obj.get("color", "#888888"),
            "portal_type": portal_info.get("portalType", "Unknown"),
            "expiring_date": portal_info.get("expiringDate", None),
        }

    def _build_connection_graph(self, map_data: List) -> dict:
        """Build a complete bidirectional graph of all connections from the map data

        Args:
            map_data: Array of map objects from Portaler API

        Returns:
            Dictionary mapping from_zone (lowercase) -> list of connection_info dicts
            Note: Zone names are normalized to lowercase for case-insensitive lookups,
                  but original case is preserved in connection_info for display.
                  Connections are bidirectional - each connection A→B also creates B→A.
        """
        graph = {}
        total_connections = 0
        skipped_connections = 0
        
        # Track existing connections for efficient O(1) deduplication
        # Format: from_zone_key -> set of to_zone_keys
        # Example: "caerleon" -> {"bridgewatch", "lymhurst", ...}
        existing_connections = {}

        for map_obj in map_data:
            portal_connections = map_obj.get("portalConnections", [])

            for connection in portal_connections:
                total_connections += 1
                info = connection.get("info", {})
                from_zone = info.get("fromZone", {})
                to_zone = info.get("toZone", {})

                from_zone_name = from_zone.get("name", "")
                to_zone_name = to_zone.get("name", "")

                if not from_zone_name or not to_zone_name:
                    skipped_connections += 1
                    continue

                # Normalize zone names to lowercase for case-insensitive lookups
                from_zone_key = from_zone_name.lower()
                to_zone_key = to_zone_name.lower()

                # Create forward and reverse connection info
                conn_info_forward = self._make_connection_info(to_zone_name, to_zone, info)
                conn_info_reverse = self._make_connection_info(from_zone_name, from_zone, info)

                # Initialize graph and deduplication tracking
                graph.setdefault(from_zone_key, [])
                graph.setdefault(to_zone_key, [])
                existing_connections.setdefault(from_zone_key, set())
                existing_connections.setdefault(to_zone_key, set())

                # Add forward connection if not duplicate (A→B)
                # Each direction is checked independently because API data may contain
                # only one direction, and we want to add the reverse even if forward exists
                if to_zone_key not in existing_connections[from_zone_key]:
                    graph[from_zone_key].append(conn_info_forward)
                    existing_connections[from_zone_key].add(to_zone_key)
                
                # Add reverse connection if not duplicate (B→A)
                if from_zone_key not in existing_connections[to_zone_key]:
                    graph[to_zone_key].append(conn_info_reverse)
                    existing_connections[to_zone_key].add(from_zone_key)

        # Count total bidirectional connections in graph
        total_graph_connections = sum(len(conns) for conns in graph.values())
        log.debug(f"Built connection graph with {len(graph)} zones")
        log.debug(f"Processed {total_connections} input connections, created {total_graph_connections} bidirectional connections")
        if skipped_connections > 0:
            log.warning(f"Skipped {skipped_connections} connections with missing zone names")
        log.debug(f"Zones in graph: {sorted(graph.keys())}")

        return graph

    def _find_connection_chains(self, graph: dict, home_zone: str, max_depth: int = 5) -> List[List[dict]]:
        """Find all connection chains starting from home zone using BFS

        Args:
            graph: Connection graph from _build_connection_graph (keys are lowercase)
            home_zone: Starting zone (will be normalized to lowercase for lookup)
            max_depth: Maximum chain length to explore

        Returns:
            List of chains, where each chain is a list of connection_info dicts
        """
        from collections import deque

        # Normalize home_zone for case-insensitive lookup
        home_zone_key = home_zone.lower()

        if home_zone_key not in graph:
            log.warning(f"Home zone '{home_zone}' not found in connection graph. Available zones: {sorted(graph.keys())}...")
            return []

        # Log connections from home zone
        home_connections = graph[home_zone_key]

        if not home_connections:
            log.warning(f"Home zone '{home_zone}' has no connections in the current data.")
            return []

        log.info(f"Found {len(home_connections)} direct connections from home zone '{home_zone}'")
        destinations = [conn['to_zone'] for conn in home_connections]
        log.debug(f"Direct connections from '{home_zone}': {destinations}")

        chains = []
        queue = deque()

        # Initialize with direct connections from home
        for conn in home_connections:
            queue.append([conn])

        while queue:
            current_chain = queue.popleft()
            last_zone = current_chain[-1]["to_zone"]
            last_zone_key = last_zone.lower()

            # Add this chain to results
            chains.append(current_chain)

            # If we haven't reached max depth and this zone has outgoing connections
            if len(current_chain) < max_depth and last_zone_key in graph:
                # Build set of all zones already in this chain path (use lowercase for comparison)
                # Include home zone and all destination zones in the chain
                chain_zones = {home_zone_key}
                chain_zones.update(conn["to_zone"].lower() for conn in current_chain)

                for next_conn in graph[last_zone_key]:
                    next_zone = next_conn["to_zone"]
                    next_zone_key = next_zone.lower()
                    # Avoid cycles by checking if this zone is already in the path
                    if next_zone_key not in chain_zones:
                        # Create new chain with this connection added
                        new_chain = current_chain + [next_conn]
                        queue.append(new_chain)

        log.debug(f"Found {len(chains)} total connection chains from '{home_zone}'")
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
            final_color = last_conn["color"]
            final_type = last_conn["type"]
            final_tier = last_conn["tier"]

            # Calculate time remaining for the first connection in chain (most critical)
            first_conn = chain[0]
            time_str = self._calculate_time_remaining(first_conn.get("expiring_date"))

            # Classify the zone
            zone_color_class = self._classify_zone_color(final_color, final_type)

            # Determine priority based on requirements:
            # 1. Royal city or portal (highest priority)
            # 2. Yellow or blue zone (medium priority)
            # 3. Black zone out of roads (lowest priority)
            is_royal = final_zone.lower() in self.ROYAL_CITIES
            
            if is_royal:
                priority = (1, len(chain))  # Royal city, prefer shorter chains
            elif zone_color_class in ['yellow', 'blue']:
                priority = (2, len(chain))  # Yellow/Blue zone, prefer shorter chains
            elif zone_color_class == 'black':
                priority = (3, len(chain))  # Black zone, prefer shorter chains
            else:
                # Other zones (red, roads, unknown) - lower priority
                priority = (4, len(chain))

            found_connections.append({
                "chain": chain,
                "final_zone": final_zone,
                "chain_length": len(chain),
                "tier": final_tier,
                "type": final_type,
                "color": final_color,
                "zone_color_class": zone_color_class,
                "time_remaining": time_str,
                "priority": priority,
                "is_royal": is_royal
            })

        # Sort by priority
        found_connections.sort(key=lambda x: (x["priority"], x["final_zone"].lower()))

        # Log summary of found connections by category
        royal_count = sum(1 for c in found_connections if c["is_royal"])
        yellow_blue_count = sum(1 for c in found_connections if c["zone_color_class"] in ['yellow', 'blue'])
        black_count = sum(1 for c in found_connections if c["zone_color_class"] == 'black')
        other_count = len(found_connections) - royal_count - yellow_blue_count - black_count
        
        log.debug(f"Processed {len(found_connections)} connections: {royal_count} royal, "
                  f"{yellow_blue_count} yellow/blue, {black_count} black, {other_count} other")

        # Apply max_connections limit if specified
        if max_connections is not None and len(found_connections) > max_connections:
            log.debug(f"Limiting connections from {len(found_connections)} to {max_connections}")
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

    def _format_no_connections_error(self, home_zone: str) -> str:
        """Format error message for when a zone has no connections

        Args:
            home_zone: The zone name that has no connections

        Returns:
            Formatted error message string
        """
        return (
            f"❌ No connections found for **{home_zone}**.\n"
            f"This zone may not exist in the current Portaler data.\n"
            f"Try setting a different home zone with `[p]setava home <zone>`."
        )

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
            Tuple of (positions dict, edges list, max_x, max_y)
            - positions: dict mapping node_id -> (x, y, node_data)
            - edges: list of (parent_node_id, child_node_id, edge_info) tuples
        """
        positions = {}
        edges = []
        node_counter = 0
        
        def assign_positions(node, depth, y_offset):
            """Recursively assign positions using depth-first traversal"""
            nonlocal node_counter
            
            # Calculate x position based on depth
            x = start_x + depth * (node_width + horizontal_spacing)
            y = y_offset
            
            # Store position with unique node ID
            node_id = f"node_{node_counter}"
            node_counter += 1
            positions[node_id] = (x, y, node)
            
            # Process children
            current_y = y_offset
            for child in node['children']:
                child_id, child_height = assign_positions(child, depth + 1, current_y)
                # Record edge from this node to child, including connection info
                edges.append((node_id, child_id, child['info']))
                current_y += child_height
            
            # Calculate total height consumed by this subtree
            if node['children']:
                # Height is from first child to last child plus one node height
                subtree_height = current_y - y_offset
            else:
                # Leaf node height
                subtree_height = node_height + vertical_spacing
            
            return node_id, subtree_height
        
        # Start positioning from root
        assign_positions(root, 0, start_y)
        
        # Calculate bounds
        max_x = max((pos[0] for pos in positions.values()), default=start_x) + node_width
        max_y = max((pos[1] for pos in positions.values()), default=start_y) + node_height
        
        return positions, edges, max_x, max_y

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
            positions, edges, max_x, max_y = self._calculate_tree_positions(
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
            for parent_id, child_id, edge_info in edges:
                if parent_id not in positions or child_id not in positions:
                    continue
                
                parent_x, parent_y, parent_node = positions[parent_id]
                child_x, child_y, child_node = positions[child_id]
                
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
                if edge_info:
                    time_str = edge_info.get('time', 'Unknown')
                    time_text = f"⏱ {time_str}"
                    time_x = (line_start_x + line_end_x) // 2
                    time_y = (line_start_y + line_end_y) // 2 - 10
                    draw.text((time_x, time_y), time_text, fill='#FFFF00',
                             font=info_font, anchor="mm")
            
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

        # Preprocess all chain parts to avoid rebuilding in nested loops
        processed_connections = []
        for conn in connections:
            chain = conn.get("chain", [])
            if not chain:
                continue
            
            # Build the chain parts for this connection
            chain_parts = [home_zone]
            for hop in chain:
                chain_parts.append(hop["to_zone"])
            
            processed_connections.append({
                'chain_parts': chain_parts,
                'prefix': chain_parts[:-1],  # Everything except the final destination
                'final_zone': conn["final_zone"],
                'tier': conn['tier'],
                'type': conn['type'],
                'time_remaining': conn['time_remaining'],
                'is_royal': conn["final_zone"].lower() in self.ROYAL_CITIES
            })

        # Group connections by their prefix
        i = 0
        while i < len(processed_connections):
            current = processed_connections[i]
            prefix = current['prefix']
            grouped = [current]
            
            # Look ahead to find connections with the same prefix
            j = i + 1
            while j < len(processed_connections):
                next_conn = processed_connections[j]
                if next_conn['prefix'] == prefix:
                    grouped.append(next_conn)
                    j += 1
                else:
                    break
            
            # Output the grouped connections
            if len(grouped) == 1:
                # Single connection, show full path
                conn = grouped[0]
                chain_str = " → ".join(conn['chain_parts'])
                royal_marker = " 👑" if conn['is_royal'] else ""
                
                lines.append(
                    f"{chain_str}{royal_marker} "
                    f"(T{conn['tier']} {conn['type']}) - "
                    f"Time: {conn['time_remaining']}"
                )
            else:
                # Multiple connections with same prefix, show prefix once
                prefix_str = " → ".join(prefix)
                
                for idx, conn in enumerate(grouped):
                    royal_marker = " 👑" if conn['is_royal'] else ""
                    
                    if idx == 0:
                        # First line shows full prefix
                        lines.append(
                            f"{prefix_str} → {conn['final_zone']}{royal_marker} "
                            f"(T{conn['tier']} {conn['type']}) - "
                            f"Time: {conn['time_remaining']}"
                        )
                    else:
                        # Subsequent lines show only the final zone with indentation
                        indent = " " * len(prefix_str)
                        lines.append(
                            f"{indent} → {conn['final_zone']}{royal_marker} "
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

    @setava.command(name="server")
    @commands.guild_only()
    async def setava_server(self, ctx, server: str):
        """Set the Albion server for this guild

        Sets which Albion server's data to filter for. Only connections from the
        specified server will be displayed.

        Valid servers: AMERICA, ASIA, EUROPE

        Usage: [p]setava server <server>
        Example: [p]setava server EUROPE
        """
        # Validate server
        server_upper = server.upper()
        if server_upper not in self.VALID_SERVERS:
            await ctx.send(
                f"❌ Invalid server. Valid servers are: {', '.join(self.VALID_SERVERS)}"
            )
            return

        await self.config.guild(ctx.guild).server.set(server_upper)
        log.debug(f"Set Albion server to '{server_upper}' for {ctx.guild.name}")
        await ctx.send(f"✅ Albion server set to **{server_upper}**")

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
                    "`[p]setava token <token>`, guild IDs are set with `[p]setava guilds <id> ...`, "
                    "or add manual connections with `[p]ava add <from> <to>`."
                )
                return

            # Get connections data (get all, we'll pick the best one)
            connections = self._get_connections_data(map_data, home_zone, max_connections=None)

            if not connections:
                await ctx.send(self._format_no_connections_error(home_zone))
                return

            # Filter to get only connections that match our criteria:
            # 1. Royal city or portal
            # 2. Yellow or blue zone
            # 3. Black zone out of roads
            suitable_connections = []
            for conn in connections:
                zone_class = conn.get('zone_color_class', 'unknown')
                is_royal = conn.get('is_royal', False)
                
                # Accept if royal, yellow, blue, or black zone
                if is_royal or zone_class in ['yellow', 'blue', 'black']:
                    suitable_connections.append(conn)
            
            # Pick the single best route (already sorted by priority)
            if suitable_connections:
                best_route = suitable_connections[0]
                # Build connection text for single route
                chain = best_route.get("chain", [])
                chain_parts = [home_zone]
                for hop in chain:
                    chain_parts.append(hop["to_zone"])
                
                chain_str = " → ".join(chain_parts)
                royal_marker = " 👑" if best_route.get('is_royal', False) else ""
                zone_class = best_route.get('zone_color_class', 'unknown')
                zone_class_display = f" ({zone_class.capitalize()} Zone)" if zone_class != 'unknown' else ""
                
                message = (
                    f"**Route from {home_zone}:**\n\n"
                    f"{chain_str}{royal_marker}{zone_class_display}\n"
                    f"Tier: T{best_route['tier']} {best_route['type']}\n"
                    f"Time remaining: {best_route['time_remaining']}"
                )
                await ctx.send(message)
            else:
                await ctx.send("No routes available")

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
                    "`[p]setava token <token>`, guild IDs are set with `[p]setava guilds <id> ...`, "
                    "or add manual connections with `[p]ava add <from> <to>`."
                )
                return

            # Get ALL connections data (no limit for image rendering)
            connections = self._get_connections_data(map_data, home_zone, max_connections=None)

            if not connections:
                await ctx.send(self._format_no_connections_error(home_zone))
                return

            # Generate graph image
            try:
                image_bytes = self._generate_graph_image(home_zone, connections)
                file = discord.File(image_bytes, filename="avalon_connections.png")
                await ctx.send(file=file)
            except Exception as e:
                log.error(f"Error generating graph image: {e}", exc_info=True)
                await ctx.send(f"❌ Failed to generate graph image: {e}")

    @ava.command(name="add")
    @checks.admin_or_permissions(manage_guild=True)
    async def ava_add(self, ctx, from_zone: str, to_zone: str, duration_hours: int = 4):
        """Add a manual connection between two zones

        Manually add a connection from one zone to another. This is useful when 
        Portaler data is unavailable or you want to track a specific connection.

        Args:
            from_zone: The starting zone name
            to_zone: The destination zone name
            duration_hours: Optional duration in hours (default: 4)

        Usage: [p]ava add <from> <to> [duration_hours]
        Example: [p]ava add Lymhurst "Thetford Portal" 4
        """
        # Validate duration
        if duration_hours < self.MIN_DURATION_HOURS:
            await ctx.send(f"❌ Duration must be at least {self.MIN_DURATION_HOURS} hour")
            return
        
        if duration_hours > self.MAX_DURATION_HOURS:
            await ctx.send(f"❌ Duration cannot exceed {self.MAX_DURATION_HOURS} hours")
            return

        # Get current manual connections
        manual_connections = await self.config.guild(ctx.guild).manual_connections()
        
        # Add new connection
        new_connection = {
            'from_zone': from_zone,
            'to_zone': to_zone,
            'duration_hours': duration_hours,
            'added_at': datetime.now(timezone.utc).isoformat()
        }
        manual_connections.append(new_connection)
        
        # Save to config
        await self.config.guild(ctx.guild).manual_connections.set(manual_connections)
        
        log.info(f"Added manual connection from '{from_zone}' to '{to_zone}' "
                 f"with duration {duration_hours}h for {ctx.guild.name}")
        
        await ctx.send(
            f"✅ Added manual connection:\n"
            f"**{from_zone}** → **{to_zone}**\n"
            f"Duration: {duration_hours} hours"
        )
