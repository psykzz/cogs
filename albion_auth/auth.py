import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

import discord
import httpx
from discord.ext import tasks
from redbot.core import commands, Config, checks

log = logging.getLogger("red.cogs.albion_auth")


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    log.debug(f"Making HTTP GET request to {url} with params: {params}")
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=10.0)

            if r.status_code == 200:
                response_data = r.json()
                log.debug(f"HTTP GET successful for {url} - Status: {r.status_code}")
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
        self.config.register_guild(
            auth_role=None,
            # {user_id: {"discord_id": int, "albion_id": str, "name": str, "last_checked": timestamp}}
            verified_users={},
            enable_daily_check=True
        )
        self._daily_check_loop.start()

    def cog_unload(self):
        """Cancel the background task when cog unloads"""
        self._daily_check_loop.cancel()
        log.debug("Cancelled daily name check task")

    async def search_player_in_region(self, name, region_url, region_name):
        """Search for a player by name in a specific region"""
        log.debug(f"Searching for player '{name}' in {region_name} region")
        params = {"q": name}
        result = await http_get(region_url, params)

        if result and result.get("players"):
            player = result["players"][0]
            log.debug(f"Player found in {region_name}: {player.get('Name')} (ID: {player.get('Id')})")
            return player, region_name

        log.debug(f"Player '{name}' not found in {region_name}")
        return None, region_name

    async def search_player(self, name):
        """Search for a player by name, checking EU first, then US and Asia as fallback"""
        log.debug(f"Searching for player: {name}")

        # Define regions to search
        regions = [
            ("https://gameinfo-ams.albiononline.com/api/gameinfo/search", "Europe"),
            ("https://gameinfo.albiononline.com/api/gameinfo/search", "US"),
            ("https://gameinfo-sgp.albiononline.com/api/gameinfo/search", "Asia"),
        ]

        # Search in Europe first
        player, region = await self.search_player_in_region(name, regions[0][0], regions[0][1])
        if player:
            log.debug(f"Player found in primary region: {player.get('Name')} (ID: {player.get('Id')})")
            return player

        # If not found in Europe, check other regions
        found_in_regions = []
        for url, region_name in regions[1:]:
            player, region = await self.search_player_in_region(name, url, region_name)
            if player:
                found_in_regions.append(region_name)

        # If found in other regions, return special result
        if found_in_regions:
            log.warning(f"Player '{name}' found in {', '.join(found_in_regions)} but not in Europe")
            return {"_found_in_other_regions": found_in_regions}

        log.warning(f"Player '{name}' not found in any region")
        return None

    @tasks.loop(hours=1.0)
    async def _daily_check_loop(self):
        """Background task to check verified users periodically"""
        log.debug("Daily check loop started")
        try:
            await self._check_users_batch()
        except Exception as e:
            log.error(f"Error in daily check loop: {e}", exc_info=True)

    @_daily_check_loop.before_loop
    async def before_daily_check(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def _check_users_batch(self):
        """Check a batch of users (approximately 1/24th of users per hour)"""
        log.debug("Starting user batch check")
        all_mismatches: List[Dict] = []

        for guild in self.bot.guilds:
            try:
                enabled = await self.config.guild(guild).enable_daily_check()
                if not enabled:
                    log.debug(f"Daily check disabled for guild {guild.name}")
                    continue

                # Get the auth role
                auth_role_id = await self.config.guild(guild).auth_role()
                if not auth_role_id:
                    log.debug(f"No auth role configured for guild {guild.name}")
                    continue

                auth_role = guild.get_role(auth_role_id)
                if not auth_role:
                    log.warning(f"Configured auth role ID {auth_role_id} not found in guild {guild.name}")
                    continue

                # Get all members with the auth role
                members_with_role = [member for member in guild.members if auth_role in member.roles]
                if not members_with_role:
                    log.debug(f"No members with auth role in guild {guild.name}")
                    continue

                verified_users = await self.config.guild(guild).verified_users()
                now = datetime.now(timezone.utc).timestamp()
                users_to_check = []

                # Build list of users to check, adding missing ones to config
                for member in members_with_role:
                    user_id_str = str(member.id)

                    # If user not in verified_users, add them with their current nickname
                    if user_id_str not in verified_users:
                        log.debug(
                            f"Adding previously verified user {member} to config "
                            f"with nickname {member.display_name}"
                        )
                        # Search for the player to get their Albion ID
                        player = await self.search_player(member.display_name)
                        # Handle special case where player found in other regions
                        if player and isinstance(player, dict) and "_found_in_other_regions" in player:
                            player = None
                        albion_id = player.get("Id") if player else None
                        albion_name = player.get("Name") if player else member.display_name

                        async with self.config.guild(guild).verified_users() as verified_users_dict:
                            verified_users_dict[user_id_str] = {
                                "discord_id": member.id,
                                "albion_id": albion_id,
                                "name": albion_name,
                                "last_checked": 0  # Set to 0 to ensure they get checked
                            }
                        # Refresh verified_users after update
                        verified_users = await self.config.guild(guild).verified_users()
                        # Small delay to avoid rate limiting when adding users
                        await asyncio.sleep(2)

                    user_data = verified_users[user_id_str]
                    last_checked = user_data.get("last_checked", 0)

                    # Check if it's been at least 24 hours
                    if now - last_checked >= 86400:  # 24 hours in seconds
                        users_to_check.append((user_id_str, user_data))

                if not users_to_check:
                    log.debug(f"No users need checking in guild {guild.name}")
                    continue

                log.debug(f"Checking {len(users_to_check)} users in guild {guild.name}")

                # Check each user and collect mismatches
                for user_id_str, user_data in users_to_check:
                    try:
                        mismatch = await self._check_single_user(guild, user_id_str, user_data)
                        if mismatch:
                            all_mismatches.append(mismatch)

                        # Small delay between checks to avoid rate limiting
                        await asyncio.sleep(2)
                    except Exception as e:
                        log.error(f"Error checking user {user_id_str}: {e}", exc_info=True)

            except Exception as e:
                log.error(f"Error checking guild {guild.name}: {e}", exc_info=True)

        # Send report if there are any mismatches
        if all_mismatches:
            await self._send_mismatch_report(all_mismatches)

    async def _check_single_user(self, guild: discord.Guild, user_id_str: str, user_data: Dict) -> Dict:
        """Check a single user's name against Albion API

        Returns a mismatch dict if there's an issue, None otherwise
        """
        user_id = int(user_id_str)
        stored_name = user_data.get("name")

        # Get the member from guild
        member = guild.get_member(user_id)
        if not member:
            log.debug(f"User {user_id} not found in guild {guild.name}")
            # Update last_checked timestamp even if user not found
            async with self.config.guild(guild).verified_users() as verified_users:
                if user_id_str in verified_users:
                    verified_users[user_id_str]["last_checked"] = datetime.now(timezone.utc).timestamp()
            return None

        # Search for player in Albion API
        player = await self.search_player(stored_name)

        # Update last_checked timestamp
        async with self.config.guild(guild).verified_users() as verified_users:
            if user_id_str in verified_users:
                verified_users[user_id_str]["last_checked"] = datetime.now(timezone.utc).timestamp()

        # Handle special case where player found in other regions
        if player and isinstance(player, dict) and "_found_in_other_regions" in player:
            regions = player["_found_in_other_regions"]
            region_list = " or ".join(regions)
            log.warning(f"Player {stored_name} found in {region_list} but not in Europe")
            return {
                "guild_name": guild.name,
                "user_id": user_id,
                "user_tag": str(member),
                "discord_nick": member.display_name,
                "stored_name": stored_name,
                "current_api_name": None,
                "issue": f"Player found on {region_list} server(s), not on European server"
            }

        if not player:
            # Player not found in API
            log.warning(f"Player {stored_name} no longer found in Albion API")
            return {
                "guild_name": guild.name,
                "user_id": user_id,
                "user_tag": str(member),
                "discord_nick": member.display_name,
                "stored_name": stored_name,
                "current_api_name": None,
                "issue": "Player not found in Albion API"
            }

        current_api_name = player.get("Name")

        # Check if names match
        if member.display_name != current_api_name:
            log.debug(f"Name mismatch for user {member}: '{member.display_name}' vs '{current_api_name}'")
            return {
                "guild_name": guild.name,
                "user_id": user_id,
                "user_tag": str(member),
                "discord_nick": member.display_name,
                "stored_name": stored_name,
                "current_api_name": current_api_name,
                "issue": "Discord nickname doesn't match Albion name"
            }

        log.debug(f"User {member} name matches: {current_api_name}")
        return None

    async def _send_mismatch_report(self, mismatches: List[Dict]):
        """Send a DM to the bot owner with the mismatch report"""
        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner

            if not owner:
                log.error("Could not determine bot owner")
                return

            # Build the report message
            report_lines = [
                "# Albion Auth Daily Check Report",
                f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                f"**Total Mismatches:** {len(mismatches)}",
                "",
                "## Details",
                ""
            ]

            for mismatch in mismatches:
                report_lines.append(f"**Guild:** {mismatch['guild_name']}")
                report_lines.append(f"**User:** {mismatch['user_tag']} (ID: {mismatch['user_id']})")
                report_lines.append(f"**Discord Nick:** {mismatch['discord_nick']}")
                report_lines.append(f"**Stored Name:** {mismatch['stored_name']}")
                if mismatch['current_api_name']:
                    report_lines.append(f"**Current Albion Name:** {mismatch['current_api_name']}")
                report_lines.append(f"**Issue:** {mismatch['issue']}")
                report_lines.append("")

            report = "\n".join(report_lines)

            # Send as DM (split if too long)
            if len(report) <= 2000:
                await owner.send(report)
            else:
                # Split into chunks
                chunks = []
                current_chunk = []
                current_length = 0

                for line in report_lines:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 1900:  # Leave some margin
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_length = line_length
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for chunk in chunks:
                    await owner.send(chunk)
                    await asyncio.sleep(1)  # Rate limit protection

            log.debug(f"Sent mismatch report to bot owner with {len(mismatches)} mismatches")

        except discord.Forbidden:
            log.error("Cannot send DM to bot owner - DMs may be disabled")
        except Exception as e:
            log.error(f"Error sending mismatch report: {e}", exc_info=True)

    @commands.guild_only()
    @commands.hybrid_command(name="auth")
    async def auth(self, ctx, name: str, target_user: discord.Member = None):
        """Authenticate with your Albion Online character name

        The bot will search for the player name in Albion Online and rename you to match.
        If an auth role is configured, it will also be assigned to you.

        Admins can optionally specify a target user to run the command on their behalf.

        Usage: .auth <player_name> [target_user]
        Example: .auth MyCharacter
        Example (admin): .auth PsyKzz @Matt
        """
        # Determine the target member (either the invoker or the specified target)
        is_admin_auth = target_user is not None
        if is_admin_auth:
            # Check if the invoker has admin permissions (administrator or manage_guild)
            has_permission = (
                ctx.author.guild_permissions.administrator
                or ctx.author.guild_permissions.manage_guild
                or await ctx.bot.is_owner(ctx.author)
            )
            if not has_permission:
                log.warning(f"Non-admin {ctx.author} tried to auth on behalf of {target_user}")
                await ctx.send("❌ Only administrators can run this command on behalf of another user.")
                return
            member = target_user
            log.debug(f"Auth command invoked by admin {ctx.author} on behalf of {member} for player: {name}")
        else:
            member = ctx.author
            log.debug(f"Auth command invoked by {ctx.author} for player: {name}")

        async with ctx.typing():
            # Search for the player
            player = await self.search_player(name)

            # Check if player was found in other regions
            if player and isinstance(player, dict) and "_found_in_other_regions" in player:
                regions = player["_found_in_other_regions"]
                if len(regions) <= 2:
                    region_list = " and ".join(regions)
                else:
                    region_list = ", ".join(regions[:-1]) + f", and {regions[-1]}"
                log.warning(
                    f"Auth command failed: Player '{name}' found in "
                    f"{region_list} but not in Europe"
                )
                await ctx.send(
                    f"❌ Player '{name}' was found on the **{region_list}** server(s), "
                    f"but not on the European server.\n"
                    f"This bot only supports authentication for players on the European server."
                )
                return

            if not player:
                log.warning(f"Auth command failed: Player '{name}' not found")
                await ctx.send(f"❌ Player '{name}' not found in Albion Online.")
                return

            player_name = player.get("Name", name)
            player_id = player.get("Id")

            log.debug(f"Found player: {player_name} (ID: {player_id})")

            # Try to rename the user
            try:
                await member.edit(nick=player_name)
                log.debug(f"Successfully renamed {member} to {player_name}")

                # Store verified user information
                async with self.config.guild(ctx.guild).verified_users() as verified_users:
                    verified_users[str(member.id)] = {
                        "discord_id": member.id,
                        "albion_id": player_id,
                        "name": player_name,
                        "last_checked": datetime.now(timezone.utc).timestamp()
                    }
                log.debug(f"Stored verified user: {member.id} -> {player_name} (Albion ID: {player_id})")

                if is_admin_auth:
                    success_msg = (
                        f"✅ Successfully authenticated {member.mention}! "
                        f"Their nickname has been changed to **{player_name}**."
                    )
                else:
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
                            await member.add_roles(auth_role)
                            success_msg += f"\n✅ Assigned the **{auth_role.name}** role."
                            log.debug(f"Assigned role {auth_role.name} to {member}")
                        except discord.Forbidden:
                            log.error(
                                f"Permission denied: Cannot assign role "
                                f"{auth_role.name} to {member}"
                            )
                            success_msg += (
                                f"\n⚠️ Could not assign the **{auth_role.name}** role "
                                "(insufficient permissions)."
                            )
                        except discord.HTTPException as e:
                            log.error(f"Failed to assign role {auth_role.name} to {member}: {e}")
                            success_msg += f"\n⚠️ Failed to assign the **{auth_role.name}** role: {e}"
                    else:
                        log.warning(f"Configured auth role ID {auth_role_id} not found in guild")
                        success_msg += (
                            "\n⚠️ The configured auth role could not be found. "
                            "Please contact an administrator."
                        )

                await ctx.send(success_msg)
            except discord.Forbidden:
                log.error(f"Permission denied: Cannot rename {member}")
                if is_admin_auth:
                    await ctx.send(
                        f"❌ I don't have permission to change {member.mention}'s nickname."
                    )
                else:
                    await ctx.send(
                        "❌ I don't have permission to change your nickname. "
                        "Please contact a server administrator."
                    )
            except discord.HTTPException as e:
                log.error(f"Failed to rename {member}: {e}")
                if is_admin_auth:
                    await ctx.send(f"❌ Failed to change {member.mention}'s nickname: {e}")
                else:
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
            log.debug(f"Auth role cleared for guild {ctx.guild.name}")
            await ctx.send("✅ Auth role has been cleared. No role will be assigned on authentication.")
        else:
            await self.config.guild(ctx.guild).auth_role.set(role.id)
            log.debug(f"Auth role set to {role.name} (ID: {role.id}) for guild {ctx.guild.name}")
            await ctx.send(f"✅ Auth role set to **{role.name}**. This role will be assigned when users authenticate.")

    @authset.command(name="dailycheck")
    async def authset_dailycheck(self, ctx, enabled: bool):
        """Enable or disable daily name verification checks

        When enabled, the bot will automatically check verified users once per day
        to ensure their Discord nickname still matches their Albion Online name.
        The bot owner will receive a DM report of any mismatches found.

        Usage: .authset dailycheck <true/false>
        Example: .authset dailycheck true
        """
        await self.config.guild(ctx.guild).enable_daily_check.set(enabled)
        log.debug(f"Daily check {'enabled' if enabled else 'disabled'} for guild {ctx.guild.name}")

        if enabled:
            await ctx.send(
                "✅ Daily name verification checks **enabled**. "
                "Verified users will be checked once per day, and the bot owner will receive "
                "a DM report of any mismatches."
            )
        else:
            await ctx.send(
                "✅ Daily name verification checks **disabled**. "
                "Automatic checking has been turned off for this server."
            )

    @authset.command(name="checkuser")
    async def authset_checkuser(self, ctx, user: discord.Member):
        """Manually check a specific user's name against Albion API

        This will immediately verify if the user's Discord nickname matches
        their Albion Online character name.

        Usage: .authset checkuser @user
        Example: .authset checkuser @JohnDoe
        """
        verified_users = await self.config.guild(ctx.guild).verified_users()
        user_id_str = str(user.id)

        if user_id_str not in verified_users:
            await ctx.send(f"❌ {user.mention} is not in the verified users list.")
            return

        user_data = verified_users[user_id_str]
        stored_name = user_data.get("name")

        async with ctx.typing():
            # Search for player in Albion API
            player = await self.search_player(stored_name)

            # Handle special case where player found in other regions
            if player and isinstance(player, dict) and "_found_in_other_regions" in player:
                regions = player["_found_in_other_regions"]
                region_list = " or ".join(regions)
                await ctx.send(
                    f"⚠️ **Mismatch Found!**\n"
                    f"User: {user.mention}\n"
                    f"Discord Nick: {user.display_name}\n"
                    f"Stored Name: {stored_name}\n"
                    f"Issue: Player found on {region_list} server(s), not on European server"
                )
                return

            if not player:
                await ctx.send(
                    f"⚠️ **Mismatch Found!**\n"
                    f"User: {user.mention}\n"
                    f"Discord Nick: {user.display_name}\n"
                    f"Stored Name: {stored_name}\n"
                    f"Issue: Player not found in Albion API"
                )
                return

            current_api_name = player.get("Name")

            if user.display_name != current_api_name:
                await ctx.send(
                    f"⚠️ **Mismatch Found!**\n"
                    f"User: {user.mention}\n"
                    f"Discord Nick: {user.display_name}\n"
                    f"Stored Name: {stored_name}\n"
                    f"Current Albion Name: {current_api_name}\n"
                    f"Issue: Discord nickname doesn't match Albion name"
                )
            else:
                await ctx.send(
                    f"✅ **No Issues**\n"
                    f"User: {user.mention}\n"
                    f"Discord Nick: {user.display_name}\n"
                    f"Albion Name: {current_api_name}\n"
                    f"Status: Names match correctly"
                )
