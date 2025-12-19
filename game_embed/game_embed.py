import logging
from typing import Optional

import a2s
import discord
from discord.ext import tasks
from redbot.core import Config, commands

IDENTIFIER = 8456723901234567890  # Random to this cog

default_guild = {
    "servers": {},  # {f"{ip}:{port}": {"ip": str, "port": int, "password": str|None}}
    "embeds": {},   # {f"{ip}:{port}": {"channel_id": int, "message_id": int}}
}

logger = logging.getLogger("red.psykzz.game_embed")


class JoinServerButton(discord.ui.View):
    """A persistent view containing a button to join a game server."""

    def __init__(self, ip: str, port: int, password: Optional[str] = None):
        super().__init__(timeout=None)

        # Build the steam connect URL
        if password:
            url = f"https://psykzz.github.io/steam-redirector/#steam://connect/{ip}:{port}/{password}"
        else:
            url = f"https://psykzz.github.io/steam-redirector/#steam://connect/{ip}:{port}"

        # Add a link button (doesn't need callback as it redirects directly)
        self.add_item(
            discord.ui.Button(
                label="Join Server",
                style=discord.ButtonStyle.link,
                url=url,
                emoji="🎮"
            )
        )


class GameEmbed(commands.Cog):
    """Monitor Steam game servers and display status embeds."""

    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)

        # Cache for server info
        self.server_cache = {}  # {f"{ip}:{port}": server_info_dict}

        # Start the background task
        self.refresh_server_data.start()

    def cog_unload(self):
        self.refresh_server_data.cancel()

    @tasks.loop(seconds=15.0)
    async def refresh_server_data(self):
        """Periodically refresh server data and update embeds."""
        logger.debug("Starting server refresh task")
        try:
            await self.update_all_servers()
        except Exception:
            logger.exception("Error in refresh task")
        logger.debug("Finished server refresh task")

    @refresh_server_data.before_loop
    async def before_refresh(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def query_server(self, ip: str, port: int) -> Optional[dict]:
        """Query a Steam server for its info using A2S protocol."""
        server_key = f"{ip}:{port}"
        cached_info = self.server_cache.get(server_key, {})

        try:
            address = (ip, port)
            # ainfo is async and has built-in timeout support
            info = await a2s.ainfo(address, timeout=5.0)
            return {
                "server_name": info.server_name,
                "game": info.game,
                "player_count": info.player_count,
                "max_players": info.max_players,
                "online": True,
            }
        except Exception as e:
            logger.warning(f"Failed to query server {ip}:{port}: {e}")
            # Use cached server_name and game when offline
            return {
                "server_name": cached_info.get("server_name", "Unknown"),
                "game": cached_info.get("game", "Unknown"),
                "player_count": 0,
                "max_players": 0,
                "online": False,
            }

    def create_server_embed(
        self,
        server_info: dict,
        ip: str,
        port: int,
        password: Optional[str] = None
    ) -> discord.Embed:
        """Create an embed for a game server."""
        if server_info.get("online"):
            color = discord.Color.green()
            status = "🟢 Online"
        else:
            color = discord.Color.red()
            status = "🔴 Offline"

        embed = discord.Embed(
            title=server_info.get("server_name", "Unknown Server"),
            color=color,
        )

        embed.add_field(
            name="Status",
            value=status,
            inline=True
        )
        embed.add_field(
            name="Game",
            value=server_info.get("game", "Unknown"),
            inline=True
        )
        embed.add_field(
            name="Players",
            value=f"{server_info.get('player_count', 0)}/{server_info.get('max_players', 0)}",
            inline=True
        )
        embed.add_field(
            name="Address",
            value=f"`{ip}:{port}`",
            inline=True
        )
        if password:
            embed.add_field(
                name="Password",
                value=f"||{password}||",
                inline=True
            )

        embed.set_footer(text="Use the button below to connect directly via Steam")
        embed.timestamp = discord.utils.utcnow()

        return embed

    async def update_all_servers(self):
        """Update all monitored servers across all guilds."""
        for guild in self.bot.guilds:
            await self.update_guild_servers(guild)

    async def update_guild_servers(self, guild: discord.Guild):
        """Update all monitored servers for a specific guild."""
        guild_config = self.config.guild(guild)
        servers = await guild_config.servers()
        embeds_config = await guild_config.embeds()

        for server_key, server_data in servers.items():
            ip = server_data["ip"]
            port = server_data["port"]
            password = server_data.get("password")

            # Query the server
            server_info = await self.query_server(ip, port)
            self.server_cache[server_key] = server_info

            # Update any posted embeds for this server
            if server_key in embeds_config:
                await self.update_embed(
                    guild,
                    embeds_config[server_key],
                    server_info,
                    ip,
                    port,
                    password
                )

    async def update_embed(
        self,
        guild: discord.Guild,
        embed_data: dict,
        server_info: dict,
        ip: str,
        port: int,
        password: Optional[str] = None
    ):
        """Update an existing embed with new server info."""
        channel_id = embed_data.get("channel_id")
        message_id = embed_data.get("message_id")

        if not channel_id or not message_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(f"Channel {channel_id} not found for embed update")
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = self.create_server_embed(server_info, ip, port, password)
            view = JoinServerButton(ip, port, password)
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            logger.warning(f"Message {message_id} not found in channel {channel_id}")
            # Clean up the embed reference
            guild_config = self.config.guild(guild)
            async with guild_config.embeds() as embeds:
                server_key = f"{ip}:{port}"
                if server_key in embeds:
                    del embeds[server_key]
        except discord.Forbidden:
            logger.warning(f"Missing permissions to edit message {message_id}")
        except discord.HTTPException as e:
            logger.warning(f"HTTP error updating embed for message {message_id}: {e.status} {e.text}")
        except Exception as e:
            logger.exception(f"Error updating embed: {e}")

    @commands.guild_only()
    @commands.group(name="gameserver", invoke_without_command=True)
    async def gameserver_group(self, ctx):
        """Game server monitoring commands."""
        await ctx.send_help()

    @gameserver_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def add_server(
        self,
        ctx,
        ip: str,
        port: int,
        password: Optional[str] = None
    ):
        """Add a Steam game server to monitor.

        Args:
            ip: The server IP address
            port: The server query port
            password: Optional server password for joining
        """
        server_key = f"{ip}:{port}"
        guild_config = self.config.guild(ctx.guild)

        async with guild_config.servers() as servers:
            if server_key in servers:
                await ctx.send(f"❌ Server `{server_key}` is already being monitored.")
                return

            servers[server_key] = {
                "ip": ip,
                "port": port,
                "password": password,
            }

        # Query the server immediately to verify it's reachable
        async with ctx.typing():
            server_info = await self.query_server(ip, port)
        self.server_cache[server_key] = server_info

        if server_info.get("online"):
            await ctx.send(
                f"✅ Added server `{server_key}` - **{server_info.get('server_name')}** "
                f"({server_info.get('game')})"
            )
        else:
            await ctx.send(
                f"⚠️ Added server `{server_key}` but it appears to be offline. "
                "The server will be monitored when it comes online."
            )

    @gameserver_group.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def remove_server(self, ctx, ip: str, port: int):
        """Remove a Steam game server from monitoring.

        Args:
            ip: The server IP address
            port: The server query port
        """
        server_key = f"{ip}:{port}"
        guild_config = self.config.guild(ctx.guild)

        async with guild_config.servers() as servers:
            if server_key not in servers:
                await ctx.send(f"❌ Server `{server_key}` is not being monitored.")
                return
            del servers[server_key]

        # Also remove any embed references
        async with guild_config.embeds() as embeds:
            if server_key in embeds:
                del embeds[server_key]

        # Remove from cache
        if server_key in self.server_cache:
            del self.server_cache[server_key]

        await ctx.send(f"✅ Removed server `{server_key}` from monitoring.")

    @gameserver_group.command(name="list")
    async def list_servers(self, ctx):
        """List all monitored Steam game servers."""
        guild_config = self.config.guild(ctx.guild)
        servers = await guild_config.servers()

        if not servers:
            await ctx.send("No servers are being monitored.")
            return

        embed = discord.Embed(
            title="🎮 Monitored Game Servers",
            color=discord.Color.blue(),
        )

        for server_key, server_data in servers.items():
            ip = server_data["ip"]
            port = server_data["port"]
            cached_info = self.server_cache.get(server_key, {})

            status = "🟢 Online" if cached_info.get("online") else "🔴 Offline"
            server_name = cached_info.get("server_name", "Unknown")
            players = f"{cached_info.get('player_count', 0)}/{cached_info.get('max_players', 0)}"

            embed.add_field(
                name=f"{status} {server_name}",
                value=f"Address: `{ip}:{port}`\nPlayers: {players}",
                inline=False
            )

        await ctx.send(embed=embed)

    @gameserver_group.command(name="post")
    @commands.admin_or_permissions(manage_guild=True)
    async def post_embed(self, ctx, ip: str, port: int):
        """Post a status embed for a monitored server.

        The embed will be automatically updated with the latest server info.

        Args:
            ip: The server IP address
            port: The server query port
        """
        server_key = f"{ip}:{port}"
        guild_config = self.config.guild(ctx.guild)
        servers = await guild_config.servers()

        if server_key not in servers:
            await ctx.send(
                f"❌ Server `{server_key}` is not being monitored. "
                "Add it first with `gameserver add`."
            )
            return

        server_data = servers[server_key]
        password = server_data.get("password")

        # Remove previous embed if one exists
        embeds_config = await guild_config.embeds()
        if server_key in embeds_config:
            old_embed_data = embeds_config[server_key]
            old_channel = ctx.guild.get_channel(old_embed_data.get("channel_id"))
            if old_channel:
                try:
                    old_message = await old_channel.fetch_message(old_embed_data.get("message_id"))
                    await old_message.delete()
                    logger.debug(f"Deleted previous embed for {server_key}")
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to delete previous embed for {server_key} in {ctx.guild.name}")
                except discord.HTTPException as e:
                    logger.warning(f"HTTP error deleting previous embed for {server_key}: {e.status} {e.text}")

        # Get current server info
        server_info = self.server_cache.get(server_key)
        if not server_info:
            async with ctx.typing():
                server_info = await self.query_server(ip, port)
            self.server_cache[server_key] = server_info

        # Create and send the embed
        embed = self.create_server_embed(server_info, ip, port, password)
        view = JoinServerButton(ip, port, password)
        message = await ctx.send(embed=embed, view=view)

        # Store the embed reference for updates
        async with guild_config.embeds() as embeds:
            embeds[server_key] = {
                "channel_id": ctx.channel.id,
                "message_id": message.id,
            }

        logger.debug(f"Posted embed for {server_key} in {ctx.guild.name}")

    @gameserver_group.command(name="refresh")
    @commands.admin_or_permissions(manage_guild=True)
    async def refresh_servers(self, ctx):
        """Manually refresh all server data and update embeds."""
        await ctx.send("🔄 Refreshing server data...")
        async with ctx.typing():
            await self.update_guild_servers(ctx.guild)
        await ctx.send("✅ Server data refreshed!")

    @gameserver_group.command(name="status")
    async def server_status(self, ctx, ip: str, port: int):
        """Get the current status of a specific server.

        Args:
            ip: The server IP address
            port: The server query port
        """
        server_key = f"{ip}:{port}"
        guild_config = self.config.guild(ctx.guild)
        servers = await guild_config.servers()

        if server_key not in servers:
            # Still allow querying non-monitored servers
            async with ctx.typing():
                server_info = await self.query_server(ip, port)
            password = None
        else:
            server_info = self.server_cache.get(server_key)
            if not server_info:
                async with ctx.typing():
                    server_info = await self.query_server(ip, port)
            password = servers[server_key].get("password")

        embed = self.create_server_embed(server_info, ip, port, password)
        view = JoinServerButton(ip, port, password)
        await ctx.send(embed=embed, view=view)
