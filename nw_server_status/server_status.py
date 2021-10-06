import httpx
import asyncio

from discord.ext import tasks
from redbot.core import commands

IDENTIFIER = 4175987634255572345  # Random to this cog

default_server = "Ishtakar"
realm_data_url = "https://nwdb.info/server-status/data.json"

class ServerStatus(commands.Cog):
    "Provider server status"

    def __init__(self, bot):
        self.bot = bot
        self.update_queue_data.start()
        
    def cog_unload(self):
        self.update_queue_data.cancel()

    @tasks.loop(seconds=30.0)
    async def update_queue_data(self):
        response = await http_get("https://nwdb.info/server-status/data.json")
        if not response.get('success'):
            return
        servers = response.get('data', {}).get('servers', [])
        self.queue_data = {server.get('worldName'): server for server in servers}

    @commands.command()
    async def queue(self, ctx, server: str = None):
        "Get current queue information"

        if server is None:
            server = default_server

        server_data = self.queue_data.get(server)
        if not server_data:
            await ctx.send(f"Can't find '{server}' in the server list.")
            return

        online = server_data.get("connectionCount", -1)
        max_online = server_data.get("connectionCountMax", -1)
        in_queue = server_data.get("queueCount", -1)
        status = server_data.get("status", -1)
        await ctx.send(f"{server}: {online}/{max_online} ~{in_queue}")



async def http_get(url):
    max_attempts = 3
    attempt = 0
    while (
        max_attempts > attempt
    ):  # httpx doesn't support retries, so we'll build our own basic loop for that
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url)

            if r.status_code == 200:
                return r.json()
            else:
                attempt += 1
            await asyncio.sleep(5)
        except (httpx._exceptions.ConnectTimeout, httpx._exceptions.HTTPError):
            attempt += 1
            await asyncio.sleep(5)
            pass
