import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import discord
from redbot.core import commands, Config
from rustplus import RustSocket, ServerDetails
from rustplus.structs import RustChatMessage

log = logging.getLogger("red.cogs.rustplus_bridge")


class RustPlusBridge(commands.Cog):
    """Bridge Discord and Rust+ team chat"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=92847361, force_registration=True)

        # Guild configuration
        self.config.register_guild(
            # Discord channel ID where messages are bridged
            bridge_channel_id=None,
            # Server connection details
            server_ip=None,
            server_port=None,
            # User who provided credentials (for permissions)
            authorized_user_id=None,
            # Player credentials
            player_id=None,
            player_token=None,
            # Bridge enabled status
            enabled=False,
        )

        # Runtime state (not persisted)
        self._connections: Dict[int, RustSocket] = {}  # guild_id -> RustSocket
        self._connection_tasks: Dict[int, asyncio.Task] = {}  # guild_id -> Task
        self._last_message_ids: Dict[int, Set[int]] = {}  # guild_id -> set of message timestamps
        self._reconnect_attempts: Dict[int, int] = {}  # guild_id -> attempt count

    async def cog_load(self):
        """Start bridge tasks for all configured guilds"""
        log.info("RustPlusBridge cog loading")
        await self.bot.wait_until_ready()

        # Start bridge tasks for all guilds that have it enabled
        for guild in self.bot.guilds:
            guild_config = await self.config.guild(guild).all()
            if guild_config.get("enabled", False):
                log.info(f"Starting bridge for guild {guild.name} ({guild.id})")
                await self._start_bridge_task(guild.id)

    async def cog_unload(self):
        """Clean up all connections and tasks"""
        log.info("RustPlusBridge cog unloading - cleaning up all connections")

        # Cancel all tasks
        for guild_id, task in list(self._connection_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Disconnect all sockets
        for guild_id, socket in list(self._connections.items()):
            try:
                socket.disconnect()
                log.info(f"Disconnected RustSocket for guild {guild_id}")
            except Exception as e:
                log.error(f"Error disconnecting socket for guild {guild_id}: {e}")

        # Clear all state
        self._connections.clear()
        self._connection_tasks.clear()
        self._last_message_ids.clear()
        self._reconnect_attempts.clear()

        log.info("RustPlusBridge cog unloaded successfully")

    async def _start_bridge_task(self, guild_id: int):
        """Start the bridge task for a guild"""
        # Cancel existing task if any
        if guild_id in self._connection_tasks:
            old_task = self._connection_tasks[guild_id]
            if not old_task.done():
                old_task.cancel()
                try:
                    await old_task
                except asyncio.CancelledError:
                    pass

        # Initialize message tracking
        if guild_id not in self._last_message_ids:
            self._last_message_ids[guild_id] = set()

        # Start new task
        task = self.bot.loop.create_task(self._bridge_loop(guild_id))
        self._connection_tasks[guild_id] = task
        log.info(f"Started bridge task for guild {guild_id}")

    async def _stop_bridge_task(self, guild_id: int):
        """Stop the bridge task for a guild"""
        # Cancel task
        if guild_id in self._connection_tasks:
            task = self._connection_tasks[guild_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._connection_tasks[guild_id]

        # Disconnect socket
        if guild_id in self._connections:
            try:
                self._connections[guild_id].disconnect()
            except Exception as e:
                log.error(f"Error disconnecting socket for guild {guild_id}: {e}")
            del self._connections[guild_id]

        # Clear message tracking
        if guild_id in self._last_message_ids:
            self._last_message_ids[guild_id].clear()

        log.info(f"Stopped bridge task for guild {guild_id}")

    async def _create_connection(self, guild_id: int) -> Optional[RustSocket]:
        """Create a RustSocket connection for a guild"""
        guild_config = await self.config.guild_from_id(guild_id).all()

        # Validate configuration
        required_fields = ["server_ip", "server_port", "player_id", "player_token"]
        for field in required_fields:
            if not guild_config.get(field):
                log.error(f"Missing required field {field} for guild {guild_id}")
                return None

        try:
            # Create server details
            server_details = ServerDetails(
                ip=guild_config["server_ip"],
                port=guild_config["server_port"],
                player_id=guild_config["player_id"],
                player_token=guild_config["player_token"]
            )

            # Create socket
            socket = RustSocket(server_details)

            # Connect
            server_addr = f"{guild_config['server_ip']}:{guild_config['server_port']}"
            log.info(f"Connecting to Rust server for guild {guild_id}: {server_addr}")
            connected = socket.connect()

            if not connected:
                log.error(f"Failed to connect to Rust server for guild {guild_id}")
                return None

            log.info(f"Successfully connected to Rust server for guild {guild_id}")
            self._reconnect_attempts[guild_id] = 0  # Reset reconnect counter
            return socket

        except Exception as e:
            log.error(f"Error creating connection for guild {guild_id}: {e}", exc_info=True)
            return None

    async def _bridge_loop(self, guild_id: int):
        """Main bridge loop for a guild"""
        log.info(f"Starting bridge loop for guild {guild_id}")

        while True:
            try:
                # Check if still enabled
                guild_config = await self.config.guild_from_id(guild_id).all()
                if not guild_config.get("enabled", False):
                    log.info(f"Bridge disabled for guild {guild_id}, stopping loop")
                    break

                # Ensure we have a connection
                if guild_id not in self._connections:
                    socket = await self._create_connection(guild_id)
                    if socket:
                        self._connections[guild_id] = socket
                    else:
                        # Failed to connect, wait before retry
                        self._reconnect_attempts[guild_id] = self._reconnect_attempts.get(guild_id, 0) + 1
                        wait_time = min(60, 5 * self._reconnect_attempts[guild_id])  # Exponential backoff, max 60s
                        attempt_num = self._reconnect_attempts[guild_id]
                        log.warning(
                            f"Failed to connect for guild {guild_id}, attempt {attempt_num}, "
                            f"retrying in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        continue

                socket = self._connections[guild_id]

                # Get team chat messages
                try:
                    chat_result = socket.get_team_chat()

                    # Check for errors
                    if hasattr(chat_result, 'error'):
                        log.error(f"Error getting team chat for guild {guild_id}: {chat_result.error}")
                        # Connection might be broken, remove it
                        del self._connections[guild_id]
                        await asyncio.sleep(5)
                        continue

                    # Process new messages
                    if isinstance(chat_result, list):
                        await self._process_rust_messages(guild_id, chat_result)

                except Exception as e:
                    log.error(f"Error in bridge loop for guild {guild_id}: {e}", exc_info=True)
                    # Remove broken connection
                    if guild_id in self._connections:
                        try:
                            self._connections[guild_id].disconnect()
                        except Exception:
                            pass
                        del self._connections[guild_id]
                    await asyncio.sleep(5)
                    continue

                # Poll interval - check for new messages every 2 seconds
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                log.info(f"Bridge loop cancelled for guild {guild_id}")
                break
            except Exception as e:
                log.error(f"Unexpected error in bridge loop for guild {guild_id}: {e}", exc_info=True)
                await asyncio.sleep(5)

        log.info(f"Bridge loop ended for guild {guild_id}")

    async def _process_rust_messages(self, guild_id: int, messages: List[RustChatMessage]):
        """Process Rust chat messages and send to Discord"""
        if not messages:
            return

        guild_config = await self.config.guild_from_id(guild_id).all()
        channel_id = guild_config.get("bridge_channel_id")

        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            log.warning(f"Bridge channel {channel_id} not found for guild {guild_id}")
            return

        # Get the set of already processed message times
        seen_times = self._last_message_ids.get(guild_id, set())

        # Process messages in chronological order (oldest first)
        new_messages = []
        for msg in reversed(messages):  # Reverse to get oldest first
            # Use timestamp as unique identifier
            msg_time = msg.time
            if msg_time not in seen_times:
                new_messages.append(msg)
                seen_times.add(msg_time)

        # Limit the size of seen_times to prevent memory issues
        if len(seen_times) > 1000:
            # Keep only the most recent 500 timestamps
            sorted_times = sorted(seen_times, reverse=True)
            seen_times.clear()
            seen_times.update(sorted_times[:500])

        # Send new messages to Discord
        for msg in new_messages:
            try:
                # Format message for Discord
                # Determine embed color from Rust message color
                if msg.colour and msg.colour.startswith('#'):
                    color = discord.Color.from_str(msg.colour)
                else:
                    color = discord.Color.orange()

                embed = discord.Embed(
                    description=msg.message,
                    color=color,
                    timestamp=datetime.fromtimestamp(msg.time, tz=timezone.utc)
                )
                embed.set_author(name=msg.name)
                embed.set_footer(text=f"Steam ID: {msg.steam_id}")

                await channel.send(embed=embed)
                log.debug(f"Forwarded message from {msg.name} to Discord in guild {guild_id}")
            except Exception as e:
                log.error(f"Error sending message to Discord for guild {guild_id}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for Discord messages and forward to Rust"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if this is a bridge channel
        if not message.guild:
            return

        guild_config = await self.config.guild(message.guild).all()

        # Check if bridge is enabled and this is the bridge channel
        if not guild_config.get("enabled", False):
            return

        if guild_config.get("bridge_channel_id") != message.channel.id:
            return

        # Check if we have a connection
        if message.guild.id not in self._connections:
            log.warning(f"No active connection for guild {message.guild.id}, cannot send message")
            return

        socket = self._connections[message.guild.id]

        try:
            # Format message for Rust (Discord username: message)
            rust_message = f"{message.author.display_name}: {message.content}"

            # Truncate if too long (Rust has message length limits)
            if len(rust_message) > 128:
                rust_message = rust_message[:125] + "..."

            # Send to Rust
            socket.send_team_message(rust_message)
            log.debug(f"Forwarded message from {message.author.display_name} to Rust in guild {message.guild.id}")

            # Add reaction to show it was sent
            await message.add_reaction("✅")

        except Exception as e:
            log.error(f"Error forwarding message to Rust for guild {message.guild.id}: {e}")
            await message.add_reaction("❌")

    @commands.group(name="rustbridge")
    @commands.guild_only()
    async def rustbridge(self, ctx):
        """RustPlus bridge commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @rustbridge.command(name="setup")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_setup(self, ctx, server_ip: str, server_port: int, player_id: int, player_token: int):
        """Setup Rust+ server connection credentials

        Example: [p]rustbridge setup 192.168.1.1 28082 12345678 87654321

        To get your player_id and player_token:
        1. Download the Rust+ mobile app
        2. Pair it with your in-game character
        3. Use a packet sniffer or check the Rust+ companion app data

        Note: You must be in a team on the Rust server for the bridge to work.
        """
        # Store configuration
        async with self.config.guild(ctx.guild).all() as guild_config:
            guild_config["server_ip"] = server_ip
            guild_config["server_port"] = server_port
            guild_config["player_id"] = player_id
            guild_config["player_token"] = player_token
            guild_config["authorized_user_id"] = ctx.author.id

        await ctx.send(
            f"✅ Rust+ credentials configured!\n"
            f"Server: `{server_ip}:{server_port}`\n"
            f"Player ID: `{player_id}`\n"
            f"Next: Set a bridge channel with `{ctx.prefix}rustbridge channel #channel`"
        )

    @rustbridge.command(name="channel")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_channel(self, ctx, channel: discord.TextChannel):
        """Set the Discord channel for the bridge

        Example: [p]rustbridge channel #rust-chat
        """
        await self.config.guild(ctx.guild).bridge_channel_id.set(channel.id)
        await ctx.send(f"✅ Bridge channel set to {channel.mention}")

    @rustbridge.command(name="enable")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_enable(self, ctx):
        """Enable the bridge

        The bridge will start forwarding messages between Discord and Rust.
        """
        guild_config = await self.config.guild(ctx.guild).all()

        # Validate configuration
        if not guild_config.get("server_ip"):
            await ctx.send(f"❌ Please setup server credentials first with `{ctx.prefix}rustbridge setup`")
            return

        if not guild_config.get("bridge_channel_id"):
            await ctx.send(f"❌ Please set a bridge channel first with `{ctx.prefix}rustbridge channel`")
            return

        # Enable and start
        await self.config.guild(ctx.guild).enabled.set(True)
        await self._start_bridge_task(ctx.guild.id)

        await ctx.send(
            f"✅ Bridge enabled! Messages will now be forwarded between "
            f"<#{guild_config['bridge_channel_id']}> and Rust team chat."
        )

    @rustbridge.command(name="disable")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_disable(self, ctx):
        """Disable the bridge

        The bridge will stop forwarding messages.
        """
        await self.config.guild(ctx.guild).enabled.set(False)
        await self._stop_bridge_task(ctx.guild.id)

        await ctx.send("✅ Bridge disabled")

    @rustbridge.command(name="status")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_status(self, ctx):
        """Check the bridge status"""
        guild_config = await self.config.guild(ctx.guild).all()

        # Build status embed
        embed = discord.Embed(title="RustPlus Bridge Status", color=discord.Color.blue())

        # Enabled status
        enabled = guild_config.get("enabled", False)
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if enabled else "🔴 Disabled",
            inline=False
        )

        # Server info
        if guild_config.get("server_ip"):
            embed.add_field(
                name="Server",
                value=f"`{guild_config['server_ip']}:{guild_config['server_port']}`",
                inline=False
            )

        # Channel info
        if guild_config.get("bridge_channel_id"):
            embed.add_field(
                name="Bridge Channel",
                value=f"<#{guild_config['bridge_channel_id']}>",
                inline=False
            )

        # Connection status
        if ctx.guild.id in self._connections:
            embed.add_field(
                name="Connection",
                value="🟢 Connected",
                inline=False
            )
        elif enabled:
            embed.add_field(
                name="Connection",
                value="🟡 Connecting...",
                inline=False
            )
        else:
            embed.add_field(
                name="Connection",
                value="⚪ Not connected",
                inline=False
            )

        # Reconnect attempts
        if ctx.guild.id in self._reconnect_attempts and self._reconnect_attempts[ctx.guild.id] > 0:
            embed.add_field(
                name="Reconnect Attempts",
                value=f"{self._reconnect_attempts[ctx.guild.id]}",
                inline=False
            )

        await ctx.send(embed=embed)

    @rustbridge.command(name="reconnect")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_reconnect(self, ctx):
        """Force a reconnection to the Rust server"""
        guild_config = await self.config.guild(ctx.guild).all()

        if not guild_config.get("enabled", False):
            await ctx.send("❌ Bridge is not enabled")
            return

        # Disconnect existing connection
        if ctx.guild.id in self._connections:
            try:
                self._connections[ctx.guild.id].disconnect()
            except Exception:
                pass
            del self._connections[ctx.guild.id]

        # Reset reconnect counter
        self._reconnect_attempts[ctx.guild.id] = 0

        await ctx.send("🔄 Reconnecting to Rust server...")

    @rustbridge.command(name="clear")
    @commands.admin_or_permissions(administrator=True)
    async def rustbridge_clear(self, ctx):
        """Clear all bridge configuration"""
        await self.config.guild(ctx.guild).clear()
        await self._stop_bridge_task(ctx.guild.id)

        await ctx.send("✅ All bridge configuration cleared")
