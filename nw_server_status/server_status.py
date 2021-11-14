import httpx
import asyncio
import logging

import discord
from discord.ext import tasks
from redbot.core import Config, commands

IDENTIFIER = 4175987634255572345  # Random to this cog

ishtakar_world_id = "3f1cd819f97e"
default_server = "Ishtakar"
realm_data_url = "https://nwdb.info/server-status/data.json"


default_guild = {
    "default_realm": "Ishtakar",
    "server_channel": None,
}

logger = logging.getLogger("red.psykzz.cogs")
logger.setLevel(logging.DEBUG)


class ServerStatus(commands.Cog):
    "Provider server status"

    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)

        self.refresh_queue_data.start()

    def cog_unload(self):
        self.refresh_queue_data.cancel()

    @tasks.loop(minutes=5.0)
    async def refresh_queue_data(self):
        logger.info("Starting queue task")
        try:
            self.queue_data = await self.get_queue_data(worldId=None)
            await self.update_monitor_channels()
        except Exception:
            logger.exception("Error in task")
        logger.info("Finished queue task")

    async def get_queue_data(self, worldId=ishtakar_world_id):
        """Refresh data from remote data"""
        try:
            extra_qs = f"worldId={worldId}" if worldId else ""
            response = await http_get(
                f"https://nwdb.info/server-status/servers.json?{extra_qs}"
            )
            if not response.get("success"):
                logger.error("Failed to get server status data")
                return
            servers = response.get("data", {}).get("servers", [])
            return {
                self.parse_server(server).get("worldName"): self.parse_server(server)
                for server in servers
            }
        except Exception:
            logger.exception("Exception while downloading new data")


    def parse_server(self, server):
        (
            connectionCountMax,
            connectionCount,
            queueCount,
            queueTime,
            worldName,
            worldSetName,
            region,
            status,
            active,
            worldId,
            a,
            b,
        ) = server
        return {
            "connectionCountMax": connectionCountMax,
            "connectionCount": connectionCount,
            "queueCount": queueCount,
            "queueTime": queueTime,
            "worldName": worldName,
            "worldSetName": worldSetName,
            "region": region,
            "status": status,
            "active": active,
            "worldId": worldId,
            "a-val": a,
            "b-val": b,
        }

    async def get_guild_monitor_channel(self, guild):
        guild_config = self.config.guild(guild)
        channel_id = await guild_config.server_channel()
        realm_name = await guild_config.default_realm()

        # Check if the channel is valid
        if not channel_id or channel_id == "0":
            logging.warn(f"Skipping {guild}...")
            return

        # If the channel doesn't exist, reset configuration and return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await guild_config.server_channel.set(None)
            return
        return channel
        

    async def update_guild_channel(self, guild):
        logger.info(f"Updating guild {guild}...")
        channel = await self.get_guild_monitor_channel(guild)

        server_status = await self.get_server_status(realm_name)
        if not server_status:
            return

        new_channel_name = server_status.split("-")[1]

        # Avoid updates if the name matches
        if channel.name == new_channel_name:
            return
        await channel.edit(name=new_channel_name)


    async def update_monitor_channels(self):
        # iterate through bot discords and get the guild config
        for guild in self.bot.guilds:
            self.update_guild_channel(guild)


    async def get_server_status(self, server_name, data=None):
        if not data:
            data = self.queue_data
        server_data = data.get(server_name)
        if not server_data:
            return "No server data available - Loading data..."

        online = server_data.get("connectionCount", -1)
        max_online = server_data.get("connectionCountMax", -1)
        in_queue_raw = int(server_data.get("queueCount", -1))
        in_queue = in_queue_raw if in_queue_raw > 1 else 0
        status = server_data.get("status", -1)
        if status == 4:
            return f"{server_name}: {online}/{max_online} Offline - Server maintenance"
        return f"{server_name}: {online}/{max_online} Online - {in_queue} in queue."


    async def get_world_id(self, server_name):
        if not self.queue_data:
            return
        server_data = self.queue_data.get(server_name)
        if not server_data:
            return
        return server_data.get("worldId")


    @commands.command()
    async def queue(self, ctx, server: str = None):
        "Get current queue information"

        if ctx.guild and server is None:
            guild_config = self.config.guild(ctx.guild)
            server = await guild_config.default_realm()

        if not server:
            await ctx.send("You must provide a server in DMs. `.queue <server>`")
            return

        worldId = await self.get_world_id(server)
        data = await self.get_queue_data(worldId=worldId)
        msg = await self.get_server_status(server, data)
        await ctx.send(msg)


    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_channels=True)
    async def monitor(self, ctx, voice_channel: discord.VoiceChannel = None):
        "Start updating a channel wth the current realm status"

        # Check if the bot has permission to the channel
        bot_perms = voice_channel.permissions_for(ctx.me)
        if not bot_perms.manage_channels:
            await ctx.send(f'I require the "Manage Channels" permission for {voice_channel.mention} to execute that command.')
            return

        guild_config = self.config.guild(ctx.guild)
        await guild_config.server_channel.set(voice_channel.id if voice_channel else None)
        if voice_channel:
            await ctx.send(f"Setup {voice_channel} as the monitor channel.")
        else:
            await ctx.send(f"Disabled monitor channel.")

    
    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @commands.admin_or_permissions(manage_channels=True)
    async def forcemonitor(self, ctx):
        "Force an update of the monitor voice channel wth the current realm status"

        voice_channel = await self.get_guild_monitor_channel(ctx.guild)
        bot_perms = voice_channel.permissions_for(ctx.me)
        if not bot_perms.manage_channels:
            await ctx.send(f'I require the "Manage Channels" permission for {voice_channel.mention} to execute that command.')
            return

        await self.update_guild_channel(ctx.guild)
        await ctx.send("Forced monitor channel update.")


    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_channels=True)
    async def queueset(self, ctx, server: str = None):
        "Set the default server for this discord server"
        guild_config = self.config.guild(ctx.guild)

        if server is None:
            realm = await guild_config.default_realm()
            await ctx.send(f"Current server: '{realm}'.")
            return

        server_data = self.queue_data.get(server)
        if not server_data:
            await ctx.send(f"Can't find '{server}' in the server list.")
            return

        await guild_config.default_realm.set(server)
        await ctx.send(f"Server updated to '{server}'.")


async def http_get(url):
    max_attempts = 3
    attempt = 0
    while (
        max_attempts > attempt
    ):  # httpx doesn't support retries, so we'll build our own basic loop for that
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers={"user-agent": "psykzz-cogs/1.0.0"})
            if r.status_code == 200:
                return r.json()
            else:
                attempt += 1
            await asyncio.sleep(5)
        except (httpx._exceptions.ConnectTimeout, httpx._exceptions.HTTPError):
            attempt += 1
            await asyncio.sleep(5)
            pass
