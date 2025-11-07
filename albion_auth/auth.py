import asyncio
import logging

import discord
import httpx
from redbot.core import commands, Config, checks

log = logging.getLogger("red.cogs.albion_auth")


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    log.info(f"Making HTTP GET request to {url} with params: {params}")
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=10.0)

            if r.status_code == 200:
                response_data = r.json()
                log.info(f"HTTP GET successful for {url} - Status: {r.status_code}")
                log.debug(f"Response data: {response_data}")
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


class AlbionAuth(commands.Cog):
    """Authenticate with Albion Online player names"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=73601, force_registration=True)
        self.config.register_guild(auth_role=None)

    async def search_player(self, name):
        """Search for a player by name"""
        log.info(f"Searching for player: {name}")
        url = "https://gameinfo-ams.albiononline.com/api/gameinfo/search"
        params = {"q": name}
        result = await http_get(url, params)

        if result and result.get("players"):
            player = result["players"][0]
            log.info(f"Player found: {player.get('Name')} (ID: {player.get('Id')})")
            return player

        log.warning(f"Player '{name}' not found in search results")
        return None

    @commands.guild_only()
    @commands.hybrid_command(name="auth")
    async def auth(self, ctx, name: str):
        """Authenticate with your Albion Online character name

        The bot will search for the player name in Albion Online and rename you to match.
        If an auth role is configured, it will also be assigned to you.

        Usage: .auth <player_name>
        Example: .auth MyCharacter
        """
        log.info(f"Auth command invoked by {ctx.author} for player: {name}")

        async with ctx.typing():
            # Search for the player
            player = await self.search_player(name)
            if not player:
                log.warning(f"Auth command failed: Player '{name}' not found")
                await ctx.send(f"❌ Player '{name}' not found in Albion Online.")
                return

            player_name = player.get("Name", name)
            player_id = player.get("Id")

            log.info(f"Found player: {player_name} (ID: {player_id})")

            # Try to rename the user
            try:
                await ctx.author.edit(nick=player_name)
                log.info(f"Successfully renamed {ctx.author} to {player_name}")
                success_msg = (
                    f"✅ Successfully authenticated! "
                    f"Your nickname has been changed to **{player_name}**."
                )

                # Check if auth role is configured and assign it
                auth_role_id = await self.config.guild(ctx.guild).auth_role()
                if auth_role_id:
                    auth_role = ctx.guild.get_role(auth_role_id)
                    if auth_role:
                        try:
                            await ctx.author.add_roles(auth_role)
                            success_msg += f"\n✅ Assigned the **{auth_role.name}** role."
                            log.info(f"Assigned role {auth_role.name} to {ctx.author}")
                        except discord.Forbidden:
                            log.error(
                                f"Permission denied: Cannot assign role "
                                f"{auth_role.name} to {ctx.author}"
                            )
                            success_msg += (
                                f"\n⚠️ Could not assign the **{auth_role.name}** role "
                                "(insufficient permissions)."
                            )
                        except discord.HTTPException as e:
                            log.error(f"Failed to assign role {auth_role.name} to {ctx.author}: {e}")
                            success_msg += f"\n⚠️ Failed to assign the **{auth_role.name}** role: {e}"
                    else:
                        log.warning(f"Configured auth role ID {auth_role_id} not found in guild")
                        success_msg += (
                            "\n⚠️ The configured auth role could not be found. "
                            "Please contact an administrator."
                        )

                await ctx.send(success_msg)
            except discord.Forbidden:
                log.error(f"Permission denied: Cannot rename {ctx.author}")
                await ctx.send(
                    "❌ I don't have permission to change your nickname. "
                    "Please contact a server administrator."
                )
            except discord.HTTPException as e:
                log.error(f"Failed to rename {ctx.author}: {e}")
                await ctx.send(f"❌ Failed to change your nickname: {e}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.group(name="authset")
    async def authset(self, ctx):
        """Configure settings for the Albion authentication system"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @authset.command(name="authrole")
    async def authset_authrole(self, ctx, role: discord.Role = None):
        """Set the role to assign when someone authenticates

        If no role is provided, clears the current auth role setting.

        Usage: .authset authrole @role
        Example: .authset authrole @Verified
        """
        if role is None:
            await self.config.guild(ctx.guild).auth_role.set(None)
            log.info(f"Auth role cleared for guild {ctx.guild.name}")
            await ctx.send("✅ Auth role has been cleared. No role will be assigned on authentication.")
        else:
            await self.config.guild(ctx.guild).auth_role.set(role.id)
            log.info(f"Auth role set to {role.name} (ID: {role.id}) for guild {ctx.guild.name}")
            await ctx.send(f"✅ Auth role set to **{role.name}**. This role will be assigned when users authenticate.")
